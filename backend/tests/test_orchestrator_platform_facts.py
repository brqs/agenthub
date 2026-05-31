"""Tests for Orchestrator platform facts and direct-answer routing."""

from __future__ import annotations

from app.agents.orchestrator import OrchestratorAdapter
from app.agents.types import ChatMessage, StreamChunk
from tests.orchestrator_fakes import (
    FakeAnswerGateway,
    FakePlannerGateway,
    FakeSubAdapter,
    _collect,
    _text_chunks,
)


async def test_orchestrator_answers_meta_question_without_planner() -> None:
    planner = FakePlannerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="planner used")]
    )
    answer = FakeAnswerGateway(_text_chunks("我是 AgentHub Orchestrator。"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 你是什么模型")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "managed_agent_ids": ["claude-code", "codex-helper"],
        },
    )

    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert answer.calls == []
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert any(
        chunk.event_type == "delta" and "AgentHub Orchestrator" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_answers_group_agents_from_conversation_context() -> None:
    planner = FakePlannerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="planner used")]
    )
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 当前群聊有哪些 agent")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                    "is_builtin": True,
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                    "is_builtin": True,
                },
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "cli", "files"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["claude-code", "codex-helper", "opencode-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert answer.calls == []
    assert "当前群聊包含 4 个 agent" in text
    assert "Orchestrator" in text
    assert "Claude Code" in text
    assert "Codex Helper" in text
    assert "OpenCode Helper" in text
    assert "Planner" not in text
    assert "Specialist Agents" not in text


async def test_orchestrator_answers_group_models_from_platform_facts() -> None:
    planner = FakePlannerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="planner used")]
    )
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 当前群聊有哪些模型")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                    "model_backend": "claude",
                    "answer_model_backend": "deepseek",
                    "planner_model_backend": "claude",
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                    "is_builtin": True,
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                    "is_builtin": True,
                    "runtime": "cli",
                    "qa_model_backend": "deepseek",
                    "qa_model": "deepseek-chat",
                },
            ],
            "managed_agent_ids": ["claude-code", "codex-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert answer.calls == []
    assert "可见的模型/运行时配置" in text
    assert "answer_model_backend: deepseek" in text
    assert "planner_model_backend: claude" in text
    assert "provider: claude_code" in text
    assert "执行模型: 未在 AgentHub 配置中暴露" in text
    assert "runtime: cli" in text
    assert "qa_model_backend: deepseek" in text
    assert "GPT-4" not in text
    assert "Gemini" not in text
    assert "Llama" not in text
    assert "Mistral" not in text


async def test_orchestrator_answers_combined_group_agents_and_self_model() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="@orchestrator 当前群聊有哪些agent，你又是什么模型",
            )
        ],
        config={
            "answer_gateway": answer,
            "model_backend": "claude",
            "answer_model_backend": "deepseek",
            "planner_model_backend": "claude",
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                    "model_backend": "claude",
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["claude-code"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "当前群聊包含 2 个 agent" in text
    assert "Claude Code" in text
    assert "我是 AgentHub Orchestrator" in text
    assert "direct answer backend: deepseek" in text
    assert "可见的模型/运行时配置" not in text


async def test_orchestrator_answers_combined_group_agents_and_self_model_variants() -> None:
    cases = [
        "@orchestrator 当前群聊有哪些 agent？你又是什么模型？",
        "@orchestrator 群里有哪些成员，你用什么后端",
        "@orchestrator 当前群聊有什么 agent？你用的是什么模型？",
        "@orchestrator 群聊里有谁？你也是什么模型？",
        "@orchestrator 当前群聊有哪些agent，以及 orchestrator 用什么模型",
        "@orchestrator what agents are in this group and what model are you?",
        "@orchestrator who is in this group, and which backend are you using?",
    ]

    for content in cases:
        answer = FakeAnswerGateway(
            [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
        )
        orchestrator = OrchestratorAdapter(agent_id="orchestrator")

        chunks = await _collect(
            orchestrator,
            messages=[ChatMessage(role="user", content=content)],
            config={
                "answer_gateway": answer,
                "model_backend": "claude",
                "answer_model_backend": "deepseek",
                "planner_model_backend": "claude",
                "conversation_agents": [
                    {
                        "id": "orchestrator",
                        "name": "Orchestrator",
                        "provider": "builtin",
                        "capabilities": ["task_decomposition", "coordination"],
                        "is_builtin": True,
                        "model_backend": "claude",
                    },
                    {
                        "id": "claude-code",
                        "name": "Claude Code",
                        "provider": "claude_code",
                        "capabilities": ["coding", "files", "analysis"],
                        "is_builtin": True,
                    },
                    {
                        "id": "codex-helper",
                        "name": "Codex Helper",
                        "provider": "codex",
                        "capabilities": ["coding", "sandbox"],
                        "is_builtin": True,
                    },
                ],
                "managed_agent_ids": ["claude-code", "codex-helper"],
            },
        )

        text = "".join(chunk.text_delta or "" for chunk in chunks)
        assert chunks[-1].event_type == "done", content
        assert answer.calls == [], content
        assert "当前群聊包含 3 个 agent" in text, content
        assert "Claude Code" in text, content
        assert "Codex Helper" in text, content
        assert "我是 AgentHub Orchestrator" in text, content
        assert "direct answer backend: deepseek" in text, content
        assert "planner backend: claude" in text, content
        assert "可见的模型/运行时配置" not in text, content


async def test_orchestrator_answers_model_followup_from_recent_context() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(role="user", content="@orchestrator 当前群聊有哪些模型"),
            ChatMessage(role="assistant", content="当前群聊可见模型如下"),
            ChatMessage(role="user", content="还有哪些模型"),
        ],
        config={
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["coordination"],
                    "is_builtin": True,
                    "model_backend": "claude",
                },
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "cli", "files"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["opencode-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "OpenCode Helper" in text
    assert "未在 AgentHub 配置中暴露" in text


async def test_orchestrator_answers_self_model_without_llm() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 你是什么模型")],
        config={
            "answer_gateway": answer,
            "model_backend": "claude",
            "answer_model_backend": "deepseek",
            "planner_model_backend": "claude",
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "我是 AgentHub Orchestrator" in text
    assert "direct answer backend: deepseek" in text
    assert "planner backend: claude" in text


async def test_orchestrator_answers_group_capabilities_from_platform_facts() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 这些 agent 能做什么")],
        config={
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["codex-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "能力配置如下" in text
    assert "task_decomposition, coordination" in text
    assert "coding, sandbox" in text


async def test_platform_fact_classifier_invalid_json_falls_back_to_direct_answer() -> None:
    classifier = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="classifier"),
            StreamChunk(event_type="delta", text_delta="not json"),
            StreamChunk(event_type="done", agent_id="classifier"),
        ]
    )
    answer = FakeAnswerGateway(
        [
            StreamChunk(event_type="start", agent_id="answer"),
            StreamChunk(event_type="delta", text_delta="direct answer"),
            StreamChunk(event_type="done", agent_id="answer"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 介绍一下")],
        config={
            "platform_fact_classifier_enabled": True,
            "platform_fact_classifier_gateway": classifier,
            "answer_gateway": answer,
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(classifier.calls) == 1
    assert len(answer.calls) == 1
    assert any(chunk.text_delta == "direct answer" for chunk in chunks)


async def test_platform_fact_classifier_low_confidence_falls_back_to_direct_answer() -> None:
    classifier = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="classifier"),
            StreamChunk(
                event_type="delta",
                text_delta=(
                    '{"intent":"platform_fact","fact_type":"group_models",'
                    '"confidence":0.2}'
                ),
            ),
            StreamChunk(event_type="done", agent_id="classifier"),
        ]
    )
    answer = FakeAnswerGateway(
        [
            StreamChunk(event_type="start", agent_id="answer"),
            StreamChunk(event_type="delta", text_delta="direct answer"),
            StreamChunk(event_type="done", agent_id="answer"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 介绍一下")],
        config={
            "platform_fact_classifier_enabled": True,
            "platform_fact_classifier_gateway": classifier,
            "answer_gateway": answer,
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(classifier.calls) == 1
    assert len(answer.calls) == 1
    assert any(chunk.text_delta == "direct answer" for chunk in chunks)


async def test_platform_fact_classifier_error_does_not_block_task_planning() -> None:
    classifier = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="classifier_error",
                error="boom",
            )
        ]
    )
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a todo app")],
        config={
            "platform_fact_classifier_enabled": True,
            "platform_fact_classifier_gateway": classifier,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(classifier.calls) == 1
    assert any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert any(chunk.text_delta == "done" for chunk in chunks)
