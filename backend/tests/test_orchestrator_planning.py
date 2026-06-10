"""Tests for Orchestrator task planning and planner failure routing."""

from __future__ import annotations

from app.agents.orchestrator import OrchestratorAdapter
from app.agents.orchestrator._internal.execution.fulfillment import (
    initialize_fulfillment,
)
from app.agents.orchestrator._internal.planning.routing import (
    is_artifact_build_request,
)
from app.agents.orchestrator._internal.planning.templates.legacy import derive_tasks
from app.agents.orchestrator._internal.routing.direct_answer import (
    _answer_messages,
    should_direct_answer,
)
from app.agents.orchestrator._internal.routing.evidence import (
    ORCHESTRATOR_EVIDENCE_HEADER,
    is_context_action_request,
    is_evidence_followup_request,
)
from app.agents.orchestrator.planner import PLANNER_SYSTEM_PROMPT, _planner_messages
from app.agents.orchestrator.task_planning import has_task_intent, resolve_tasks
from app.agents.orchestrator.types import OrchestratorRunContext
from app.agents.types import ChatMessage, StreamChunk
from tests.orchestrator_fakes import (
    FakeAnswerGateway,
    FakePlannerGateway,
    FakeSubAdapter,
    FakeWorkspaceWriterAdapter,
    _task,
    _text_chunks,
)
from tests.orchestrator_fakes import (
    _collect as _collect_base,
)


async def _collect(adapter, config=None, messages=None, workspace_path=None):
    stream_config = dict(config or {})
    stream_config.setdefault("clarification_gate_enabled", False)
    return await _collect_base(
        adapter,
        config=stream_config,
        messages=messages,
        workspace_path=workspace_path,
    )


class FakeMultiFileWriterAdapter(FakeSubAdapter):
    def __init__(
        self,
        agent_id: str,
        chunks: list[StreamChunk],
        files: dict[str, str],
    ) -> None:
        super().__init__(agent_id, chunks)
        self.files = files

    async def stream(
        self,
        messages,
        *,
        system_prompt=None,
        config=None,
        workspace_path=None,
        tool_specs=None,
    ):
        if workspace_path is not None:
            for relative_path, content in self.files.items():
                target = workspace_path / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        async for chunk in super().stream(
            messages,
            system_prompt=system_prompt,
            config=config,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
        ):
            yield chunk


def test_legacy_template_creates_conversation_tasks_for_debate_request() -> None:
    request = (
        "@orchestrator 组织群组内两个智能体开展辩论，论题是AI的快速发展对人类社会"
        "利大于弊还是弊大于利？不需要生成文件直接以对话的形式输出，注意是"
        "对话场景而不是书面书写。"
    )

    tasks = derive_tasks(
        {
            "managed_agent_ids": [
                "orchestrator",
                "codex-helper",
                "claude-code",
                "opencode-helper",
            ]
        },
        [ChatMessage(role="user", content=request)],
    )

    assert [task.task_id for task in tasks] == ["dialogue-turn-1", "dialogue-turn-2"]
    assert [task.task_type for task in tasks] == ["dialogue_turn", "dialogue_turn"]
    assert all(task.expected_output == "" for task in tasks)
    assert [task.agent_id for task in tasks] == ["claude-code", "opencode-helper"]
    assert tasks[1].depends_on == ("dialogue-turn-1",)
    assert all("Analyze request" not in task.title for task in tasks)


def test_legacy_template_creates_dialogue_turn_tasks_for_turn_taking_request() -> None:
    request = (
        "@orchestrator 组织群组内两个智能体开展辩论，论题是AI的快速发展对人类社会"
        "利大于弊还是弊大于利？不需要生成文件直接以对话的形式输出。"
        "由 Claude Code 先开始，一人一句回应对方，结尾可以 @另一个agent。"
    )

    tasks = derive_tasks(
        {
            "managed_agent_ids": [
                "orchestrator",
                "codex-helper",
                "claude-code",
                "opencode-helper",
            ]
        },
        [ChatMessage(role="user", content=request)],
    )

    assert [task.task_id for task in tasks] == ["dialogue-turn-1", "dialogue-turn-2"]
    assert [task.task_type for task in tasks] == ["dialogue_turn", "dialogue_turn"]
    assert [task.agent_id for task in tasks] == ["claude-code", "opencode-helper"]
    assert tasks[0].depends_on == ()
    assert tasks[1].depends_on == ("dialogue-turn-1",)
    assert all(task.expected_output == "" for task in tasks)
    assert "不要代写其他 Agent" in tasks[0].instruction
    assert "必须明确回应" in tasks[1].instruction


def test_legacy_template_creates_generic_roundtable_tasks_without_ai_hardcode() -> None:
    request = (
        "@orchestrator 不需要生成文件，请组织两个智能体做圆桌讨论，主题是"
        "中小企业是否应该接入 AI 客服。直接以群聊对话形式输出。"
    )

    tasks = derive_tasks(
        {"managed_agent_ids": ["orchestrator", "claude-code", "opencode-helper"]},
        [ChatMessage(role="user", content=request)],
    )

    assert len(tasks) == 2
    assert [task.task_type for task in tasks] == ["dialogue_turn", "dialogue_turn"]
    assert all(task.expected_output == "" for task in tasks)
    assert all("中小企业是否应该接入 AI 客服" in task.instruction for task in tasks)
    assert all("AI 的快速发展对人类社会" not in task.instruction for task in tasks)
    assert all("不要主持" in task.instruction for task in tasks)


def test_legacy_template_creates_dialogue_turn_tasks_for_data_panel() -> None:
    request = (
        "@orchestrator 不需要生成文件，请让两个智能体分析这组数据："
        "渠道 A 转化率 12%、渠道 B 转化率 7%、渠道 C 转化率 15%，预算分别为"
        " 30/20/10 万。请直接在群聊里给出结论、依据和下一步建议。"
    )

    tasks = derive_tasks(
        {"managed_agent_ids": ["orchestrator", "claude-code", "opencode-helper"]},
        [ChatMessage(role="user", content=request)],
    )

    assert [task.task_type for task in tasks] == ["dialogue_turn", "dialogue_turn"]
    assert [task.agent_id for task in tasks] == ["claude-code", "opencode-helper"]
    assert all(task.expected_output == "" for task in tasks)
    assert all("渠道 A 转化率" in task.instruction for task in tasks)


async def test_turn_taking_request_uses_deterministic_tasks_before_planner() -> None:
    request = (
        "@orchestrator 不需要生成文件，请让两个智能体分析这组数据："
        "渠道 A 转化率 12%、渠道 B 转化率 7%、渠道 C 转化率 15%，预算分别为"
        " 30/20/10 万。请直接在群聊里给出结论、依据和下一步建议。"
    )
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )

    tasks = await resolve_tasks(
        {
            "planner_gateway": planner,
            "managed_agent_ids": ["orchestrator", "claude-code", "opencode-helper"],
        },
        [ChatMessage(role="user", content=request)],
        None,
    )

    assert planner.calls == []
    assert [task.task_type for task in tasks] == ["dialogue_turn", "dialogue_turn"]
    assert [task.agent_id for task in tasks] == ["claude-code", "opencode-helper"]


async def test_single_planner_conversation_task_rebalances_to_two_agents() -> None:
    request = (
        "@orchestrator 组织群组内两个智能体开展辩论，论题是AI的快速发展对人类社会"
        "利大于弊还是弊大于利？不需要生成文件直接以对话的形式输出。"
    )
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "dialogue",
                            "codex-helper",
                            "Debate dialogue",
                            "Create a group debate dialogue. Do not create files.",
                            task_type="conversation",
                        )
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    claude = FakeSubAdapter(
        "claude-code",
        _text_chunks(
            "正方：我认为 AI 快速发展利大于弊，因为它能提升医疗、教育和生产效率，"
            "让更多普通人获得智能工具支持。风险需要治理，但不能掩盖整体收益。"
        ),
    )
    opencode = FakeSubAdapter(
        "opencode-helper",
        _text_chunks(
            "针对上一轮正方提到的医疗和教育收益，反方：我认为 AI 快速发展弊大于利，"
            "因为就业替代、隐私泄露和治理滞后可能先于收益集中爆发。"
            "社会需要先建立约束，再扩大应用范围。"
        ),
    )

    chunks = await _collect(
        OrchestratorAdapter(agent_id="orchestrator"),
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code", "opencode-helper"]
    assert claude.received_messages
    assert opencode.received_messages


def test_planner_prompt_references_agent_capability_profile_rule() -> None:
    assert "capability profile" in PLANNER_SYSTEM_PROMPT
    assert "user-scope v2 capability profile" in PLANNER_SYSTEM_PROMPT
    assert "stronger recent" in PLANNER_SYSTEM_PROMPT
    assert "clearly" in PLANNER_SYSTEM_PROMPT
    assert "stronger agent" in PLANNER_SYSTEM_PROMPT
    assert "current" in PLANNER_SYSTEM_PROMPT
    assert "request" in PLANNER_SYSTEM_PROMPT
    assert "override historical" in PLANNER_SYSTEM_PROMPT
    assert "Do not probe a" in PLANNER_SYSTEM_PROMPT
    assert "outside the available agents list" in PLANNER_SYSTEM_PROMPT
    assert "must not" in PLANNER_SYSTEM_PROMPT
    assert "profile, strengths, weaknesses" in PLANNER_SYSTEM_PROMPT
    assert "split implementation work across distinct implementation-capable agents" in (
        PLANNER_SYSTEM_PROMPT
    )
    assert "planning_profile" in PLANNER_SYSTEM_PROMPT
    assert "Do not infer" in PLANNER_SYSTEM_PROMPT
    assert "provider or agent id" in PLANNER_SYSTEM_PROMPT
    assert "alone; choose each agent" in PLANNER_SYSTEM_PROMPT
    assert "codex-helper as the lead architect" not in PLANNER_SYSTEM_PROMPT
    assert "codex-helper as the technical lead" not in PLANNER_SYSTEM_PROMPT


def test_generic_template_review_task_is_independent_review() -> None:
    tasks = derive_tasks(
        {"managed_agent_ids": ["codex-helper", "claude-code", "opencode-helper"]},
        [
            ChatMessage(
                role="user",
                content=(
                    "我要做一个网站，先生成一份文档，包含代码产物、Diff，"
                    "最后进行审阅。"
                ),
            )
        ],
    )

    assert tasks[1].expected_output.endswith("diff.md")
    assert tasks[2].task_type == "review"
    assert tasks[2].depends_on == ("auto-1", "auto-2")
    assert tasks[2].review_of == ("auto-1", "auto-2")


def test_command_fulfillment_extracts_diff_in_chinese_sentence() -> None:
    context = OrchestratorRunContext()

    initialize_fulfillment(context, "请生成代码产物、Diff、审阅并部署。")

    assert any(item["id"] == "diff" for item in context.fulfillment_items)


def test_command_fulfillment_does_not_treat_strategy_option_as_document() -> None:
    context = OrchestratorRunContext()

    initialize_fulfillment(
        context,
        "不需要生成文件，请讨论风险、成本、治理角度和替代方案，不要写报告。",
    )

    assert not any(item["id"] == "document" for item in context.fulfillment_items)


def test_command_fulfillment_still_detects_explicit_document() -> None:
    context = OrchestratorRunContext()

    initialize_fulfillment(context, "请先生成一份设计文档，然后再实现。")

    assert any(item["id"] == "document" for item in context.fulfillment_items)


def test_command_fulfillment_explicit_markdown_overrides_no_file_hint() -> None:
    context = OrchestratorRunContext()

    initialize_fulfillment(context, "不需要其他文件，只生成 planning.md。")

    assert any(item["id"] == "document" for item in context.fulfillment_items)


async def test_orchestrator_planner_receives_only_whitelisted_memory_signals() -> None:
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("created document"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "create-document",
                            "opencode-helper",
                            "Create document",
                            "Create report.md.",
                        )
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    memory = (
        "Agent capability profile v2 from recent user Orchestrator runs:\n"
        "- @claude-code: success_rate=0.0; score=-1.2; confidence=low\n"
        "- @opencode-helper: success_rate=1.0; score=2.1; confidence=medium\n\n"
        "User preference memory from recent Orchestrator runs:\n"
        "domains: document=3\n"
        "language_style_hints: chinese=2\n\n"
        "Agent capability profile from recent Orchestrator runs:\n"
        "- @claude-code: success_count=0; failure_count=1\n"
        "- @opencode-helper: success_count=1; failure_count=0\n\n"
        "Previous Orchestrator structured memory:\n"
        "private historical details that the planner does not need"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(role="system", content=memory),
            ChatMessage(role="user", content="Create report.md"),
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper"],
            "sub_adapters": {"opencode-helper": opencode},
        },
    )

    assert chunks[-1].event_type == "done"
    planner_message = planner.calls[0]["messages"][0].content
    assert "Orchestrator memory signals available to planner:" in planner_message
    assert "Agent capability profile v2 from recent user Orchestrator runs" in planner_message
    assert "User preference memory from recent Orchestrator runs" in planner_message
    assert "@opencode-helper: success_rate=1.0; score=2.1" in planner_message
    assert "@opencode-helper: success_count=1; failure_count=0" in planner_message
    assert "language_style_hints: chinese=2" in planner_message
    assert "private historical details" not in planner_message


def test_artifact_design_requests_are_task_intent_not_direct_answer() -> None:
    snake_request = (
        "\u8bf7\u4f60\u8bbe\u8ba1\u4e00\u4e2a\u7f51\u9875\u7248\u7684"
        "\u8d2a\u5403\u86c7\u6e38\u620f\uff0c\u8981\u6c42\u5185\u5bb9\u7cbe\u81f4"
    )
    campus_request = (
        "\u8bbe\u8ba1\u4e00\u4e2a\u4e2d\u56fd\u79d1\u5b66\u6280\u672f"
        "\u5927\u5b66\u6821\u56ed\u5c55\u793a\u7f51\u9875"
    )

    assert is_artifact_build_request(snake_request)
    assert is_artifact_build_request(campus_request)
    assert has_task_intent(snake_request)
    assert has_task_intent(campus_request)
    assert not is_artifact_build_request("\u4f60\u597d")
    assert not is_artifact_build_request("Build just a launch plan")


def test_context_followup_request_routes_to_evidence_answer() -> None:
    request = "主题是赛博朋克风的网站生成了吗"
    messages = [ChatMessage(role="user", content=f"@orchestrator {request}")]

    assert has_task_intent(request)
    assert is_evidence_followup_request(request)
    assert not is_context_action_request(request)
    assert should_direct_answer(
        {"managed_agent_ids": ["codex-helper"]},
        messages,
        latest_user_request=lambda items: items[-1].content,
        agent_id_list=lambda _value: ["codex-helper"],
        explicit_agent_mentions=lambda _agent_ids, _request: [],
        strip_orchestrator_mention=lambda text: text.replace("@orchestrator", "").strip(),
        has_task_intent=has_task_intent,
    )


async def test_context_followup_does_not_call_planner() -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(event_type="delta", text_delta="not json"),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(role="user", content="主题是赛博朋克风的网站生成了吗"),
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["codex-helper"],
        },
    )

    visible_text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert planner.calls == []
    assert chunks[-1].event_type == "done"
    assert "invalid_task_plan" not in visible_text
    assert "当前会话" in visible_text


def test_context_action_request_evidence_pack_is_planner_whitelisted() -> None:
    assert is_context_action_request("继续完成缺失的部署")
    assert not is_evidence_followup_request("继续完成缺失的部署")

    planner_messages = _planner_messages(
        {},
        [
            ChatMessage(
                role="system",
                content=(
                    f"{ORCHESTRATOR_EVIDENCE_HEADER}\n"
                    "- latest_run_status: done\n"
                    "- files: planning.md, index.html\n"
                    "- preview: url=http://example.test/index.html\n"
                ),
            ),
            ChatMessage(role="user", content="继续完成缺失的部署"),
        ],
        "继续完成缺失的部署",
        ["codex-helper"],
    )

    planner_content = planner_messages[0].content
    assert ORCHESTRATOR_EVIDENCE_HEADER in planner_content
    assert "latest_run_status: done" in planner_content
    assert "planning.md" in planner_content


async def test_orchestrator_planner_cannot_select_agent_outside_available_agents() -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="delta",
                text_delta=(
                    '{"tasks":[{"task_id":"task-a","agent_id":"outside-agent",'
                    '"title":"Design","instruction":"Build UI"}]}'
                ),
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a landing page")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["codex-helper"],
            "available_agents": [
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding"],
                    "is_builtin": True,
                }
            ],
        },
    )

    assert len(planner.calls) == 1
    assert "- codex-helper" in planner.calls[0]["messages"][0].content
    assert "outside-agent" not in planner.calls[0]["messages"][0].content
    assert chunks[-1].event_type == "error"
    assert "unknown agent_id 'outside-agent'" in (chunks[-1].error or "")
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)


async def test_orchestrator_planner_receives_safe_planning_profiles() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("done"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "implement",
                            "claude-code",
                            "Implement",
                            "Create files.",
                        )
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a page")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code"],
            "available_agents": [
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files"],
                    "is_builtin": True,
                    "planning_profile": "并行实现主力",
                    "planning_strengths": ["implementation", "parallel_execution"],
                    "planning_weaknesses": ["global_architecture_ownership"],
                    "preferred_task_types": ["implementation", "repair"],
                    "command": "claude",
                    "args": ["--danger"],
                    "sdk_options": {"permission_mode": "acceptEdits"},
                    "api_key": "should-not-leak",
                    "token": "should-not-leak",
                }
            ],
            "sub_adapters": {"claude-code": claude},
        },
    )

    planner_message = planner.calls[0]["messages"][0].content
    assert chunks[-1].event_type == "done"
    assert "planning_profile=并行实现主力" in planner_message
    assert "strengths=implementation, parallel_execution" in planner_message
    assert "weaknesses=global_architecture_ownership" in planner_message
    assert "preferred_task_types=implementation, repair" in planner_message
    assert "command=" not in planner_message
    assert "args=" not in planner_message
    assert "sdk_options" not in planner_message
    assert "api_key" not in planner_message
    assert "token" not in planner_message


async def test_orchestrator_planner_prompt_includes_safe_planning_profiles() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("planned review"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "review",
                            "codex-helper",
                            "Review implementation",
                            "Review the implementation and report issues.",
                        )
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Plan and review this work")],
        config={
            "planner_gateway": planner,
            "sub_adapters": {"codex-helper": codex},
            "available_agents": [
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                    "planning_profile": "总负责人，负责 architecture、review 和 escalation",
                    "planning_strengths": ["architecture", "final_review"],
                    "planning_weaknesses": ["routine_parallel_implementation"],
                    "preferred_task_types": ["planning", "review", "escalation"],
                    "api_key": "should-not-leak",
                    "env": {"TOKEN": "hidden"},
                    "command": "secret-command",
                    "args": ["--secret"],
                    "sdk_options": {"token": "hidden"},
                    "runtime_available": True,
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files"],
                    "planning_profile": "并行实现主力之一",
                    "planning_strengths": ["implementation", "code_review"],
                    "preferred_task_types": ["implementation", "repair", "review"],
                    "runtime_available": True,
                },
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "cli"],
                    "planning_profile": "并行实现主力之二",
                    "planning_strengths": ["parallel_execution", "verification"],
                    "preferred_task_types": ["implementation", "verification"],
                    "runtime_available": True,
                },
                {
                    "id": "custom-codex-runtime",
                    "name": "Custom Codex",
                    "provider": "codex",
                    "capabilities": ["testing"],
                    "system_prompt_summary": "自建 agent 只使用自己的摘要。",
                    "runtime_available": True,
                },
            ],
        },
    )

    assert chunks[-1].event_type == "done"
    planner_message = planner.calls[0]["messages"][0].content
    assert "planning_profile=总负责人，负责 architecture、review 和 escalation" in planner_message
    assert "strengths=architecture, final_review" in planner_message
    assert "weaknesses=routine_parallel_implementation" in planner_message
    assert "preferred_task_types=planning, review, escalation" in planner_message
    assert "planning_profile=并行实现主力之一" in planner_message
    assert "planning_profile=并行实现主力之二" in planner_message
    assert "system_prompt_summary=自建 agent 只使用自己的摘要。" in planner_message
    assert planner_message.count("总负责人，负责 architecture") == 1
    assert "api_key" not in planner_message
    assert "should-not-leak" not in planner_message
    assert "TOKEN" not in planner_message
    assert "secret-command" not in planner_message
    assert "sdk_options" not in planner_message


async def test_orchestrator_direct_routing_only_matches_current_managed_agents() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("claude response"))
    codex = FakeSubAdapter("codex-helper", _text_chunks("codex response"))
    planner = FakePlannerGateway([])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    '@orchestrator ask claude code, codex, and outside-agent '
                    '"hello" and return their outputs'
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code", "codex-helper"]
    assert not any(chunk.to_agent == "outside-agent" for chunk in chunks)


async def test_orchestrator_plans_tasks_with_llm_tool_call() -> None:
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "task-b",
                            "agent-b",
                            "Second",
                            "Reply from agent-b.",
                            priority=2,
                        ),
                        _task(
                            "task-a",
                            "agent-a",
                            "First",
                            "Reply from agent-a.",
                            priority=1,
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Ask both agents who they are")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert adapter_a.received_messages[-1].content == "Reply from agent-a."
    assert adapter_b.received_messages[-1].content == "Reply from agent-b."
    assert planner.calls[0]["tools"][0].name == "submit_task_plan"
    assert planner.calls[0]["config"]["tool_choice"] == {"type": "auto"}
    assert "Ask both agents who they are" in planner.calls[0]["messages"][0].content
    assert "Port preview/deploy requests must not become" in (
        planner.calls[0]["messages"][0].content
    )
    assert "Do not create tasks that start, deploy, preview" in (
        planner.calls[0]["system_prompt"] or ""
    )


async def test_orchestrator_balances_explicit_multi_agent_group_plan() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("from codex"))
    claude = FakeSubAdapter("claude-code", _text_chunks("from claude"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("from opencode"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "architecture",
                            "codex-helper",
                            "Create architecture",
                            "Create strategy-architecture.md.",
                            priority=1,
                        ),
                        _task(
                            "journey",
                            "codex-helper",
                            "Create journey",
                            "Create customer-journey.md.",
                            priority=2,
                        ),
                        _task(
                            "risk",
                            "codex-helper",
                            "Create risk review",
                            "Create risk-review.md.",
                            priority=3,
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 请用真实 Agent 群聊完成文档策略任务，至少两个"
                    "可用 Agent 要在自己的独立消息中分工。"
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    switched_agents = [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ]
    assert switched_agents == [
        "codex-helper",
        "claude-code",
        "opencode-helper",
        "codex-helper",
    ]
    assert "Create customer-journey.md." in claude.received_messages[-1].content
    assert "Create customer-journey.md." in opencode.received_messages[-1].content
    assert "Create risk-review.md." in codex.received_messages[-1].content


async def test_orchestrator_balances_to_explicitly_mentioned_group_agents() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("from codex"))
    claude = FakeSubAdapter("claude-code", _text_chunks("from claude"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("from opencode"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task("doc-a", "codex-helper", "Doc A", "Create a.md."),
                        _task(
                            "doc-b",
                            "codex-helper",
                            "Doc B",
                            "Create b.md.",
                            priority=2,
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 请使用 Claude Code 和 OpenCode Helper 两个可用 "
                    "Agent 按真实分工完成文档任务。"
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code", "opencode-helper"]
    assert claude.received_messages
    assert opencode.received_messages
    assert codex.received_messages == []


async def test_orchestrator_rebalances_chinese_parallel_development_request() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("codex output"))
    claude = FakeSubAdapter("claude-code", _text_chunks("claude output"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("opencode output"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "design-doc",
                            "codex-helper",
                            "生成赛博朋克网站设计文档",
                            "Create cyberpunk-website-design.md.",
                            priority=1,
                        ),
                        _task(
                            "frontend-page",
                            "codex-helper",
                            "实现赛博朋克前端页面",
                            "Create index.html, styles.css and app.js.",
                            priority=2,
                        ),
                        _task(
                            "interaction-polish",
                            "codex-helper",
                            "完善交互和移动端适配",
                            "Polish button interactions and responsive layout.",
                            priority=3,
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 我要做一个网站，主题是赛博朋克风，先生成一份文档，"
                    "然后交由两个智能体并行开发工作，最后再进行审阅，最后进行部署"
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    switched_agents = [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ]
    assert chunks[-1].event_type == "done"
    assert len(set(switched_agents)) >= 2
    assert switched_agents == ["codex-helper", "claude-code", "opencode-helper"]
    assert "Create cyberpunk-website-design.md." in codex.received_messages[-1].content
    assert "Create index.html, styles.css and app.js." in (
        claude.received_messages[-1].content
    )
    assert "Polish button interactions" in opencode.received_messages[-1].content


async def test_orchestrator_splits_single_parallel_development_task() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("codex output"))
    claude = FakeSubAdapter("claude-code", _text_chunks("claude output"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("opencode output"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "design-doc",
                            "codex-helper",
                            "生成赛博朋克风网站设计文档",
                            "Create cyberpunk-website-design.md.",
                            priority=1,
                        ),
                        _task(
                            "parallel-frontend",
                            "codex-helper",
                            "并行开发 - 实现赛博朋克风前端页面",
                            "Create index.html, styles.css and app.js.",
                            priority=2,
                        ),
                        {
                            **_task(
                                "final-review",
                                "codex-helper",
                                "审阅最终生成的网站文件",
                                "Review all generated website files.",
                                priority=4,
                            ),
                            "task_type": "review",
                            "depends_on": ["parallel-frontend"],
                            "review_of": ["parallel-frontend"],
                        },
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 我要做一个网站，主题是赛博朋克风，先生成一份文档，"
                    "然后交由两个智能体并行开发工作，最后再进行审阅，最后进行部署"
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    switched_agents = [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ]
    assert chunks[-1].event_type == "done"
    assert switched_agents == [
        "codex-helper",
        "claude-code",
        "opencode-helper",
        "codex-helper",
    ]
    assert "primary implementation slice" in claude.received_messages[-1].content
    assert "complementary implementation" in opencode.received_messages[-1].content
    assert any(
        "Review all generated website files." in message.content
        for message in codex.received_messages
    )


async def test_orchestrator_splits_single_chained_implementation_for_multi_agent_request() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("codex output"))
    claude = FakeSubAdapter("claude-code", _text_chunks("claude output"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("opencode output"))
    review_task = _task(
        "task-3-review",
        "codex-helper",
        "Review and verify cyberpunk website implementation",
        "Review the implemented cyberpunk website files.",
        priority=3,
        depends_on=["task-2-impl"],
    )
    review_task["task_type"] = "review"
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "task-1-doc",
                            "codex-helper",
                            "Generate cyberpunk website specification document",
                            "Create spec-cyberpunk.md.",
                            priority=1,
                        ),
                        _task(
                            "task-2-impl",
                            "codex-helper",
                            "Implement cyberpunk website with button interactions",
                            "Create index.html, styles.css, app.js and Diff evidence.",
                            priority=2,
                            depends_on=["task-1-doc"],
                        ),
                        review_task,
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 我要做一个网站，主题是赛博朋克风，先生成一份文档，"
                    "然后交由两个智能体并行开发工作，包含代码产物、Diff、按钮交互和移动端适配，"
                    "最后再进行审阅，最后部署在端口8082，并完成浏览器级质量验收。"
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "codex-helper", "opencode-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    switched_agents = [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ]
    assert chunks[-1].event_type == "done"
    assert switched_agents == [
        "codex-helper",
        "claude-code",
        "opencode-helper",
        "codex-helper",
    ]
    task_card = next(
        chunk
        for chunk in chunks
        if chunk.event_type == "block_start" and chunk.block_type == "task_card"
    )
    task_ids = [
        task["id"] for task in (task_card.metadata or {}).get("tasks", [])
    ]
    assert "task-2-impl-parallel-2" in task_ids
    assert "primary implementation slice" in claude.received_messages[-1].content
    assert "complementary implementation" in opencode.received_messages[-1].content


async def test_orchestrator_reassigns_planner_self_review_to_independent_agent() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("implementation done"))
    claude = FakeSubAdapter("claude-code", _text_chunks("review done"))
    review_task = _task(
        "review",
        "codex-helper",
        "审阅所有生成的文件",
        "Review the implementation files.",
        priority=2,
        depends_on=["implementation"],
    )
    review_task["task_type"] = "review"
    review_task["review_of"] = ["implementation"]
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "implementation",
                            "codex-helper",
                            "实现网站",
                            "Create the website artifacts.",
                            priority=1,
                        ),
                        review_task,
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="@orchestrator 实现一个网站，然后最后再进行审阅。",
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["codex-helper", "claude-code"],
            "sub_adapters": {
                "codex-helper": codex,
                "claude-code": claude,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["codex-helper", "claude-code"]
    assert "Create the website artifacts." in codex.received_messages[-1].content
    assert "Review the implementation files." in claude.received_messages[-1].content


async def test_orchestrator_preserves_explicit_requirements_in_planned_tasks() -> None:
    adapter = FakeSubAdapter("claude-code", _text_chunks("created demo"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "create-demo",
                            "claude-code",
                            "Create themed frontend",
                            "Create a random themed frontend demo.",
                        )
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    request = (
        "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff 和网页预览的"
        "前端开发演示，主题随机，部署在端口8082"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code"],
            "sub_adapters": {"claude-code": adapter},
        },
    )

    assert chunks[-1].event_type == "done"
    instruction = adapter.received_messages[-1].content
    assert request in instruction
    assert "Preserve every explicit deliverable" in instruction
    assert "conventional static frontend structure" in instruction
    assert len(planner.calls) == 1
    assert "Preserve explicit acceptance requirements" in (
        planner.calls[0]["messages"][0].content
    )


async def test_frontend_deploy_planner_output_is_not_overridden_by_quality_template() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("claude plan only"))
    codex = FakeSubAdapter("codex-helper", _text_chunks("created files"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("reviewed files"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "planner-claude",
                            "claude-code",
                            "Analyze request",
                            "Analyze the frontend request.",
                        )
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    request = (
        "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff、网页预览、"
        "按钮交互和移动端适配的前端开发演示，主题随机，部署在端口8082，"
        "并完成浏览器级质量验收"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(planner.calls) == 1
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code"]
    assert any(
        "I'll handle this in 1 step(s)" in (chunk.text_delta or "") for chunk in chunks
    )
    assert any(
        "Analyze request" in (chunk.text_delta or "") for chunk in chunks
    )
    assert not any(
        "Design frontend demo architecture" in (chunk.text_delta or "") for chunk in chunks
    )
    assert "Analyze the frontend request." in claude.received_messages[-1].content
    assert "移动端适配" in claude.received_messages[-1].content
    assert codex.received_messages == []
    assert opencode.received_messages == []


async def test_frontend_deploy_empty_planner_tasks_uses_command_fallback() -> None:
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("created files"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={"tasks": []},
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    request = (
        "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff、网页预览、"
        "按钮交互和移动端适配的前端开发演示，并行执行，主题赛博朋克风，"
        "部署在端口8082，并完成浏览器级质量验收"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "opencode-helper": opencode,
                "claude-code": FakeSubAdapter("claude-code", _text_chunks("created page")),
                "codex-helper": FakeSubAdapter("codex-helper", _text_chunks("created plan")),
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(planner.calls) == 1
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "codex-helper",
        "claude-code",
        "opencode-helper",
    ]
    assert opencode.received_messages


async def test_fullstack_delivery_uses_deterministic_parallel_dag() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("created frontend"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("created backend"))
    codex = FakeSubAdapter("codex-helper", _text_chunks("created review"))
    planner = FakePlannerGateway([])
    request = (
        "@orchestrator 请完成一个前后端产品交付演示，主题是“团队 OKR 轻量看板”。"
        "先产出 planning.md，然后并行调度 claude-code 生成 index.html、styles.css、"
        "app.js，并让 opencode-helper 生成 backend_app.py、api.md、backend_tests.md。"
        "最后调度 codex-helper 生成 review.md，并部署到端口8082。"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "opencode-helper": opencode,
                "codex-helper": codex,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["codex-helper", "claude-code", "opencode-helper", "codex-helper"]
    assert any("I'll handle this in 4 step(s)" in (chunk.text_delta or "") for chunk in chunks)
    assert any("Implement frontend artifacts" in (chunk.text_delta or "") for chunk in chunks)
    assert any("Implement backend artifacts" in (chunk.text_delta or "") for chunk in chunks)
    assert any("Review fullstack delivery" in (chunk.text_delta or "") for chunk in chunks)
    assert "Do not automatically request same-origin API URLs" in (
        claude.received_messages[-1].content
    )
    assert "backend_app.py, api.md, backend_tests.md" in (
        opencode.received_messages[-1].content
    )
    assert "frontend/backend API consistency" in codex.received_messages[-1].content


async def test_fullstack_delivery_template_does_not_hardcode_okr_theme() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("created frontend"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("created backend"))
    codex = FakeSubAdapter("codex-helper", _text_chunks("created review"))
    request = (
        "@orchestrator 请完成一个前后端产品交付演示，主题是“客户支持工单平台”。"
        "产出 planning.md、index.html、styles.css、app.js、backend_app.py、api.md、"
        "backend_tests.md 和 review.md。"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "managed_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "opencode-helper": opencode,
                "codex-helper": codex,
            },
        },
    )

    all_instructions = "\n".join(
        message.content
        for adapter in (claude, opencode, codex)
        for message in adapter.received_messages
    )
    assert chunks[-1].event_type == "done"
    assert "客户支持工单平台" in all_instructions
    assert "团队 OKR 轻量看板" not in all_instructions
    assert "/api/okrs" not in all_instructions


async def test_orchestrator_filters_planner_port_service_tasks() -> None:
    frontend_agent = FakeSubAdapter("frontend-agent", _text_chunks("created snake.html"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "task-create",
                            "frontend-agent",
                            "Create snake.html",
                            "Create a complete snake.html game file.",
                        ),
                        _task(
                            "task-preview",
                            "claude-code",
                            "Start 8082 preview service",
                            "Set up the port preview service and verify the game.",
                            priority=2,
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="Create snake.html and preview it on port 8082.",
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["frontend-agent", "claude-code"],
            "sub_adapters": {"frontend-agent": frontend_agent},
        },
    )

    planning_text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "I'll handle this in 1 step(s)" in planning_text
    assert "Create snake.html" in planning_text
    assert "via LLM planner/config" not in planning_text
    assert "Start 8082 preview service" not in planning_text
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["frontend-agent"]


async def test_orchestrator_plans_tasks_from_llm_json_text() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta=(
                    '```json\n{"tasks":[{"task_id":"task-a","agent_id":"agent-a",'
                    '"title":"Answer","instruction":"Answer directly.",'
                    '"priority":0}]}\n```'
                ),
            ),
            StreamChunk(event_type="block_end", block_index=0),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "agent-a"
    ]
    assert adapter_a.received_messages[-1].content == "Answer directly."


async def test_orchestrator_rejects_planner_unknown_agent() -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="tool_call",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task("task-a", "unknown-agent", "Bad", "Do work"),
                    ]
                },
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": FakeSubAdapter("agent-a", _text_chunks("unused"))},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "invalid_task_plan"
    assert "unknown agent_id" in (chunks[1].error or "")


async def test_orchestrator_planner_error_does_not_use_template_by_default() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="timeout",
                error="planner timeout",
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "missing_task_plan"
    assert "timeout: planner timeout" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_planner_error_uses_command_fulfillment_fallback(
    tmp_path,
) -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="timeout",
                error="planner timeout",
            )
        ]
    )
    codex = FakeWorkspaceWriterAdapter(
        "codex-helper",
        _text_chunks("Created planning.md"),
        "planning.md",
        "# Plan\n\nCommand fallback plan.",
    )
    claude = FakeMultiFileWriterAdapter(
        "claude-code",
        _text_chunks("Created frontend artifacts"),
        {
            "index.html": (
                "<!doctype html><html><head><link rel='stylesheet' "
                "href='styles.css'></head><body><button id='demo'>Demo</button>"
                "<script src='app.js'></script></body></html>"
            ),
            "styles.css": "button { min-height: 44px; }",
            "app.js": "document.getElementById('demo')?.addEventListener('click', () => {});",
        },
    )
    opencode = FakeWorkspaceWriterAdapter(
        "opencode-helper",
        _text_chunks("Created review.md"),
        "review.md",
        (
            "# Review\n\n"
            "PASS. The fallback plan, frontend artifact set, button interaction "
            "hook, responsive touch target, and deployment handoff requirements "
            "were checked against the original request. Remaining platform "
            "preview and deployment work is handled by Orchestrator tools."
        ),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 我要做一个网站，先生成一份文档，然后交由两个智能体"
                    "并行开发工作，最后进行审阅和部署。"
                ),
            )
        ],
        workspace_path=tmp_path,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["codex-helper", "claude-code", "opencode-helper"],
            "sub_adapters": {
                "codex-helper": codex,
                "claude-code": claude,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["codex-helper", "claude-code", "opencode-helper"]
    assert (tmp_path / "planning.md").exists()
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "review.md").exists()


async def test_orchestrator_planner_empty_output_is_visible_error() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway([])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "missing_task_plan"
    assert "empty_planner_output" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_planner_invalid_json_is_visible_error() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="not a task plan",
            ),
            StreamChunk(event_type="block_end", block_index=0),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "invalid_task_plan"
    assert "invalid_json" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_planner_invalid_json_can_fallback_to_direct_answer() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="not a task plan",
            ),
            StreamChunk(event_type="block_end", block_index=0),
        ]
    )
    answer = FakeAnswerGateway(_text_chunks("Direct answer fallback."))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "direct_answer_on_planner_failure": True,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(planner.calls) == 1
    assert len(answer.calls) == 1
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert any(chunk.text_delta == "Direct answer fallback." for chunk in chunks)
    assert adapter_a.received_messages == []


async def test_artifact_planner_invalid_json_is_visible_error_not_direct_answer() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("created snake game"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(event_type="delta", block_index=0, text_delta="not a task plan"),
            StreamChunk(event_type="block_end", block_index=0),
        ]
    )
    answer = FakeAnswerGateway(_text_chunks("I will delegate this to a specialist."))
    request = (
        "\u8bf7\u4f60\u8bbe\u8ba1\u4e00\u4e2a\u7f51\u9875\u7248\u7684"
        "\u8d2a\u5403\u86c7\u6e38\u620f\uff0c\u8981\u6c42\u5185\u5bb9\u7cbe\u81f4"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "direct_answer_on_planner_failure": True,
            "managed_agent_ids": ["claude-code"],
            "available_agents": [
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files"],
                    "is_builtin": True,
                }
            ],
            "sub_adapters": {"claude-code": claude},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[-1].error_code == "invalid_task_plan"
    assert len(planner.calls) == 1
    assert answer.calls == []
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert claude.received_messages == []


async def test_artifact_planner_error_does_not_invoke_unavailable_runtime() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("created snake game"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("should not run"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(event_type="delta", block_index=0, text_delta="not a task plan"),
            StreamChunk(event_type="block_end", block_index=0),
        ]
    )
    request = (
        "\u8bf7\u4f60\u8bbe\u8ba1\u4e00\u4e2a\u7f51\u9875\u7248\u7684"
        "\u8d2a\u5403\u86c7\u6e38\u620f\uff0c\u8981\u6c42\u5185\u5bb9\u7cbe\u81f4"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "direct_answer_on_planner_failure": True,
            "managed_agent_ids": ["opencode-helper", "claude-code"],
            "available_agents": [
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "runtime_status": "unavailable",
                    "runtime_available": False,
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files"],
                },
            ],
            "sub_adapters": {
                "claude-code": claude,
                "opencode-helper": opencode,
            },
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[-1].error_code == "invalid_task_plan"
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert claude.received_messages == []
    assert opencode.received_messages == []


async def test_artifact_planner_failure_without_available_agent_is_error() -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(event_type="delta", block_index=0, text_delta="not a task plan"),
            StreamChunk(event_type="block_end", block_index=0),
        ]
    )
    answer = FakeAnswerGateway(_text_chunks("I will delegate this to a specialist."))
    request = (
        "\u8bf7\u4f60\u8bbe\u8ba1\u4e00\u4e2a\u7f51\u9875\u7248\u7684"
        "\u8d2a\u5403\u86c7\u6e38\u620f"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "direct_answer_on_planner_failure": True,
            "managed_agent_ids": [],
            "available_agents": [],
            "sub_adapters": {},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "no_runnable_agent"
    assert "no executable agent is available" in (chunks[1].error or "")
    assert answer.calls == []
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)


async def test_scoped_empty_available_agents_do_not_fall_back_to_global_managed_agents() -> None:
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("should not run"))
    request = (
        "\u8bf7\u4f60\u8bbe\u8ba1\u4e00\u4e2a\u7f51\u9875\u7248\u7684"
        "\u8d2a\u5403\u86c7\u6e38\u620f"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "managed_agent_ids": ["opencode-helper", "claude-code"],
            "available_agents": [],
            "available_agents_authoritative": True,
            "conversation_scoped_agents": True,
            "sub_adapters": {"opencode-helper": opencode},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "no_runnable_agent"
    assert "no executable agent is available" in (chunks[1].error or "")
    assert opencode.received_messages == []


async def test_scoped_available_agents_allow_opencode_only_when_in_current_scope() -> None:
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("created snake game"))
    request = (
        "\u8bf7\u4f60\u8bbe\u8ba1\u4e00\u4e2a\u7f51\u9875\u7248\u7684"
        "\u8d2a\u5403\u86c7\u6e38\u620f"
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content=request)],
        config={
            "managed_agent_ids": ["claude-code"],
            "available_agents": [
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "files"],
                    "runtime_available": True,
                    "runtime_status": "ready",
                }
            ],
            "available_agents_authoritative": True,
            "conversation_scoped_agents": True,
            "sub_adapters": {"opencode-helper": opencode},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["opencode-helper"]
    assert opencode.received_messages


def test_direct_answer_preserves_structured_memory_context() -> None:
    messages = [
        ChatMessage(
            role="system",
            content="Previous Orchestrator structured memory:\n- done @claude-code build",
        ),
        ChatMessage(role="user", content="\u4f60\u4e4b\u524d\u6709\u4ec0\u4e48\u4efb\u52a1"),
    ]

    answer_messages = _answer_messages(
        messages,
        latest_user_request=lambda items: items[-1].content,
    )

    assert answer_messages[0].role == "system"
    assert answer_messages[0].content.startswith(
        "Previous Orchestrator structured memory"
    )
    assert "structured memory above" in answer_messages[1].content


async def test_orchestrator_planner_template_fallback_requires_flag() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="timeout",
                error="planner timeout",
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "planner_fallback_to_template": True,
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert any("I'll handle this in 2 step(s)" in (chunk.text_delta or "") for chunk in chunks)
    assert all("via legacy template" not in (chunk.text_delta or "") for chunk in chunks)
    assert adapter_a.received_messages[-1].content.startswith("Analyze the user's request")


async def test_orchestrator_generic_fallback_prefers_codex_architect_role() -> None:
    codex = FakeSubAdapter("codex-helper", _text_chunks("architecture done"))
    claude = FakeSubAdapter("claude-code", _text_chunks("implementation done"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("review done"))
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="timeout",
                error="planner timeout",
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a product launch checklist")],
        config={
            "planner_gateway": planner,
            "planner_fallback_to_template": True,
            "managed_agent_ids": [
                "opencode-helper",
                "claude-code",
                "codex-helper",
            ],
            "sub_adapters": {
                "codex-helper": codex,
                "claude-code": claude,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["codex-helper", "claude-code", "opencode-helper"]
    assert codex.received_messages[-1].content.startswith("Analyze the user's request")
    assert "product launch checklist" in codex.received_messages[-1].content
    assert claude.received_messages
    assert opencode.received_messages
