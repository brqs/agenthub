"""Tests for Orchestrator final response presentation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.orchestrator._internal.execution.fulfillment import (
    fulfillment_needs_attention,
    initialize_fulfillment,
    mark_task_fulfillment,
)
from app.agents.orchestrator._internal.execution.presentation import (
    presented_response_text,
)
from app.agents.orchestrator._internal.execution.process_block import (
    contains_forbidden_process_text,
    execution_process_block,
)
from app.agents.orchestrator.evaluation import EvaluationResult
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


class FakePolishGateway:
    def __init__(self, text: str = "", *, error: bool = False) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "config": config,
                "tools": tools,
            }
        )
        yield StreamChunk(event_type="start", agent_id="polish")
        if self.error:
            yield StreamChunk(
                event_type="error",
                agent_id="polish",
                error_code="upstream_error",
                error="boom",
            )
            return
        if self.text:
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(event_type="delta", block_index=0, text_delta=self.text)
            yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id="polish")


def _context() -> tuple[list[SubTask], dict[str, TaskState], OrchestratorRunContext]:
    task = SubTask(
        task_id="task-a",
        agent_id="agent-a",
        title="Write report",
        instruction="Create report.md",
        expected_output="report.md",
    )
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        state=TaskState.SUCCEEDED,
        artifact_paths=["report.md"],
        evaluation_results=[
            EvaluationResult(
                evaluator="document_quality",
                status="passed",
                passed=True,
                checked_artifacts=["report.md"],
            )
        ],
    )
    result = TaskResult(
        task_id=task.task_id,
        title=task.title,
        final_state=TaskState.SUCCEEDED,
        attempts=[attempt],
    )
    context = OrchestratorRunContext()
    context.record(result)
    return [task], {task.task_id: TaskState.SUCCEEDED}, context


async def test_deterministic_summary_filters_internal_trace_terms() -> None:
    tasks, states, context = _context()

    text = await presented_response_text(
        {},
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\nTools: Read(report.md) result ok call_123\n",
    )

    assert "Execution summary" not in text
    assert "Tools:" not in text
    assert "result ok" not in text
    assert "call_" not in text
    assert "Write report" in text
    assert "report.md" in text
    assert "validation check(s) passed" in text


def test_code_artifact_fulfillment_accepts_artifact_paths() -> None:
    task = SubTask(
        task_id="frontend",
        agent_id="claude-code",
        title="Build frontend",
        instruction="Create index.html, styles.css, and app.js",
    )
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="claude-code",
        state=TaskState.SUCCEEDED,
        artifact_paths=["index.html", "styles.css", "app.js"],
    )
    context = OrchestratorRunContext()
    context.record(
        TaskResult(
            task_id=task.task_id,
            title=task.title,
            final_state=TaskState.SUCCEEDED,
            attempts=[attempt],
        )
    )
    initialize_fulfillment(context, "我要做一个网站，包含代码产物。")

    mark_task_fulfillment(
        context,
        [task],
        {task.task_id: TaskState.SUCCEEDED},
    )

    assert fulfillment_needs_attention(context) == []


async def test_pending_tasks_make_visible_summary_partial() -> None:
    tasks, states, context = _context()
    pending = SubTask(
        task_id="task-b",
        agent_id="agent-b",
        title="Publish follow-up",
        instruction="Publish the report.",
    )

    text = await presented_response_text(
        {},
        [ChatMessage(role="user", content="Create and publish a report")],
        [*tasks, pending],
        {**states, pending.task_id: TaskState.PENDING},
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert "Done. I completed the requested work." not in text
    assert "I completed the parts that could be finished" in text
    assert "Publish follow-up" in text
    assert "was not run before orchestration stopped" in text


async def test_non_platform_fulfillment_pending_makes_visible_summary_partial() -> None:
    tasks, states, context = _context()
    context.fulfillment_items = [
        {
            "id": "review",
            "label": "审阅/复核",
            "status": "pending",
            "evidence": [],
            "reason": "没有确认独立审阅完成。",
        }
    ]

    text = await presented_response_text(
        {},
        [ChatMessage(role="user", content="Create and review a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert "Done. I completed the requested work." not in text
    assert "I completed the parts that could be finished" in text
    assert "审阅/复核: 没有确认独立审阅完成。" in text


async def test_platform_fulfillment_pending_does_not_contradict_later_tools() -> None:
    tasks, states, context = _context()
    context.fulfillment_items = [
        {
            "id": "deployment",
            "label": "部署/发布",
            "status": "pending",
            "evidence": [],
            "reason": "尚未完成平台部署。",
        },
        {
            "id": "browser_verify",
            "label": "浏览器质量验收",
            "status": "pending",
            "evidence": [],
            "reason": "尚未完成浏览器级验收。",
        }
    ]

    text = await presented_response_text(
        {},
        [ChatMessage(role="user", content="Create and deploy a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert "Done. I completed the requested work." in text
    assert "尚未完成平台部署" not in text
    assert "尚未完成浏览器级验收" not in text


async def test_polish_success_uses_model_output() -> None:
    tasks, states, context = _context()
    gateway = FakePolishGateway("Done. I wrote `report.md` and validation passed.")

    text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": gateway,
            "orchestrator_response_polish_max_tokens": 321,
        },
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert text == "Done. I wrote `report.md` and validation passed.\n"
    assert gateway.calls[0]["config"]["max_tokens"] == 321
    assert "raw_summary_excerpt" not in gateway.calls[0]["messages"][0].content
    assert "Write report" in gateway.calls[0]["messages"][0].content
    assert context.llm_control_points == [
        {
            "phase": "response_polish",
            "model_backend": "test_gateway",
            "status": "succeeded",
            "used_llm": True,
            "fallback_reason": None,
            "decision_summary": "Response polish produced the final user-facing answer.",
        }
    ]


async def test_polish_forbidden_or_empty_output_falls_back() -> None:
    tasks, states, context = _context()
    forbidden = FakePolishGateway("Observation: Tool read result ok call_abc")
    missing_member_output = FakePolishGateway(
        "两位成员已发言，但发言具体内容未保留，可以重新发起辩论查看。"
    )
    empty = FakePolishGateway("")

    forbidden_text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": forbidden,
        },
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )
    missing_member_text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": missing_member_output,
        },
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )
    empty_text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": empty,
        },
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert "Observation:" not in forbidden_text
    assert "call_" not in forbidden_text
    assert "Write report" in forbidden_text
    assert "未保留" not in missing_member_text
    assert "重新发起辩论" not in missing_member_text
    assert missing_member_text == forbidden_text
    assert empty_text == forbidden_text
    assert [point["status"] for point in context.llm_control_points] == [
        "fallback",
        "fallback",
        "failed",
    ]
    assert [point["phase"] for point in context.llm_control_points] == [
        "response_polish",
        "response_polish",
        "response_polish",
    ]


async def test_polish_local_server_command_falls_back() -> None:
    tasks, states, context = _context()
    gateway = FakePolishGateway(
        "需要你手动执行 `python3 -m http.server 8082` 来预览页面。"
    )

    text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": gateway,
        },
        [ChatMessage(role="user", content="创建并部署网站")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert "python3 -m http.server" not in text
    assert "手动执行" not in text
    assert "Write report" in text


async def test_polish_missing_dialogue_judgement_falls_back() -> None:
    pro = SubTask(
        task_id="dialogue-pro",
        agent_id="claude-code",
        title="正方发言",
        instruction="正方发言，不要生成文件。",
        task_type="dialogue_turn",
    )
    con = SubTask(
        task_id="dialogue-con",
        agent_id="opencode-helper",
        title="反方发言",
        instruction="反方发言，不要生成文件。",
        task_type="dialogue_turn",
        depends_on=("dialogue-pro",),
    )
    context = OrchestratorRunContext()
    context.record(
        TaskResult(
            task_id=pro.task_id,
            title=pro.title,
            final_state=TaskState.SUCCEEDED,
            attempts=[
                TaskAttempt(
                    attempt_index=1,
                    agent_id=pro.agent_id,
                    state=TaskState.SUCCEEDED,
                    text_preview="正方认为 AI 发展利大于弊。",
                )
            ],
        )
    )
    context.record(
        TaskResult(
            task_id=con.task_id,
            title=con.title,
            final_state=TaskState.SUCCEEDED,
            attempts=[
                TaskAttempt(
                    attempt_index=1,
                    agent_id=con.agent_id,
                    state=TaskState.SUCCEEDED,
                    text_preview="反方认为 AI 发展弊大于利。",
                )
            ],
        )
    )
    context.debate_judgement = {
        "type": "llm_dialogue_judgement",
        "mode": "debate",
        "winner_label": "正方（claude-code）",
        "summary": "双方围绕 AI 发展利弊完成辩论。",
        "reason": "正方给出的治理路径更具可操作性。",
    }
    gateway = FakePolishGateway("辩论已经完成，双方观点都已呈现。")

    text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": gateway,
        },
        [ChatMessage(role="user", content="请辩论 AI 发展的利处和弊处")],
        [pro, con],
        {pro.task_id: TaskState.SUCCEEDED, con.task_id: TaskState.SUCCEEDED},
        context,
        "Execution summary\n- succeeded\n",
    )

    assert "辩论裁判" in text
    assert "正方（claude-code）" in text
    assert "辩论已经完成，双方观点都已呈现。" not in text


async def test_polish_missing_fallback_debate_judgement_falls_back() -> None:
    pro = SubTask(
        task_id="dialogue-pro",
        agent_id="claude-code",
        title="正方发言",
        instruction="正方发言，不要生成文件。",
        task_type="dialogue_turn",
    )
    con = SubTask(
        task_id="dialogue-con",
        agent_id="opencode-helper",
        title="反方发言",
        instruction="反方发言，不要生成文件。",
        task_type="dialogue_turn",
        depends_on=("dialogue-pro",),
    )
    context = OrchestratorRunContext()
    for task, preview in (
        (pro, "正方认为 AI 发展利大于弊。"),
        (con, "反方认为 AI 发展弊大于利。"),
    ):
        context.record(
            TaskResult(
                task_id=task.task_id,
                title=task.title,
                final_state=TaskState.SUCCEEDED,
                attempts=[
                    TaskAttempt(
                        attempt_index=1,
                        agent_id=task.agent_id,
                        state=TaskState.SUCCEEDED,
                        text_preview=preview,
                    )
                ],
            )
        )
    context.debate_judgement = {
        "type": "debate_judgement",
        "winner": "draw",
        "winner_label": "势均力敌",
        "scores": {"pro": 6, "con": 7},
        "reason": "双方均给出了有力回应和充分论据。",
    }
    gateway = FakePolishGateway(
        "### 最终评判\n双方势均力敌。\n\n未完成独立的第三方审阅复核环节。"
    )

    text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": gateway,
        },
        [ChatMessage(role="user", content="请辩论 AI 发展的利处和弊处")],
        [pro, con],
        {pro.task_id: TaskState.SUCCEEDED, con.task_id: TaskState.SUCCEEDED},
        context,
        "Execution summary\n- succeeded\n",
    )

    assert "辩论评判" in text
    assert "势均力敌" in text
    assert "未完成独立的第三方审阅" not in text


async def test_process_block_marks_pending_tasks_partial_and_sanitizes_terms() -> None:
    tasks, states, context = _context()
    pending = SubTask(
        task_id="task-b",
        agent_id="agent-b",
        title="Publish follow-up",
        instruction="Publish the report.",
    )

    payload = execution_process_block(
        [ChatMessage(role="user", content="Create and publish a report")],
        [*tasks, pending],
        {**states, pending.task_id: TaskState.PENDING},
        context,
    )

    assert payload["status"] == "partial"
    assert payload["steps"][2]["status"] == "skipped"
    assert "task-b" not in str(payload)
    assert not contains_forbidden_process_text(payload)
