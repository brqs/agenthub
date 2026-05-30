"""Tests for Orchestrator task planning and planner failure routing."""

from __future__ import annotations

from app.agents.orchestrator import OrchestratorAdapter
from app.agents.types import ChatMessage, StreamChunk
from tests.orchestrator_fakes import (
    FakeAnswerGateway,
    FakePlannerGateway,
    FakeSubAdapter,
    _collect,
    _task,
    _text_chunks,
)


async def test_orchestrator_planner_cannot_select_agent_outside_available_agents() -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="delta",
                text_delta=(
                    '{"tasks":[{"task_id":"task-a","agent_id":"web-designer",'
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
    assert "web-designer" not in planner.calls[0]["messages"][0].content
    assert chunks[-1].event_type == "error"
    assert "unknown agent_id 'web-designer'" in (chunks[-1].error or "")
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)


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
                    '@orchestrator ask claude code, codex, and web-designer '
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
    assert not any(chunk.to_agent == "web-designer" for chunk in chunks)


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
    assert "Preserve explicit acceptance requirements" in (
        planner.calls[0]["messages"][0].content
    )


async def test_orchestrator_filters_planner_port_service_tasks() -> None:
    web_designer = FakeSubAdapter("web-designer", _text_chunks("created snake.html"))
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
                            "web-designer",
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
            "managed_agent_ids": ["web-designer", "claude-code"],
            "sub_adapters": {"web-designer": web_designer},
        },
    )

    planning_text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "via LLM planner/config" in planning_text
    assert "Start 8082 preview service" not in planning_text
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["web-designer"]


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
    assert any(
        "via legacy template" in (chunk.text_delta or "") for chunk in chunks
    )
    assert adapter_a.received_messages[-1].content.startswith("Analyze the user's request")
