"""Tests for Orchestrator ReAct dynamic task graph execution."""

from __future__ import annotations

from app.agents.orchestrator import OrchestratorAdapter
from app.agents.types import ChatMessage, StreamChunk
from tests.orchestrator_fakes import (
    FakeSubAdapter,
    SequencedGateway,
    _collect,
    _react_decision_chunks,
    _task,
    _text_chunks,
)


async def test_orchestrator_react_disabled_preserves_static_flow() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    react_gateway = SequencedGateway(
        [_react_decision_chunks('{"actions":[{"type":"finish"}],"summary":"unused"}')]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": False,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "Static", "Run static task")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert chunks[-1].event_type == "done"
    assert react_gateway.calls == []
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "agent-a"
    ]
    assert not any("ReAct step" in (chunk.text_delta or "") for chunk in chunks)


async def test_orchestrator_react_trace_can_be_explicitly_shown() -> None:
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    react_gateway = SequencedGateway(
        [_react_decision_chunks('{"actions":[{"type":"finish","reason":"done"}]}')]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_trace_visible": True,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "One", "Run one")],
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "ReAct step 1" in text
    assert "Action: finish: done" in text


async def test_orchestrator_react_adds_fix_task_after_failure_and_finishes() -> None:
    verify = FakeSubAdapter(
        "opencode-helper",
        [
            StreamChunk(
                event_type="error",
                error_code="verification_failed",
                error="missing click behavior",
            )
        ],
    )
    fix = FakeSubAdapter("codex-helper", _text_chunks("Fixed click behavior"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"add_task","task":{'
                '"task_id":"fix-html","agent_id":"codex-helper",'
                '"title":"Fix HTML behavior",'
                '"instruction":"Fix the missing click behavior.",'
                '"priority":2}}],'
                '"summary":"thought: add repair task"}'
            ),
            _react_decision_chunks(
                '{"actions":[{"type":"finish","reason":"Fixed and verified"}],"summary":"done"}'
            ),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Fix and verify an HTML file")],
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [
                _task(
                    "verify-html",
                    "opencode-helper",
                    "Verify HTML",
                    "Verify the click behavior.",
                )
            ],
            "managed_agent_ids": ["codex-helper", "opencode-helper"],
            "sub_adapters": {
                "opencode-helper": verify,
                "codex-helper": fix,
            },
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert len(react_gateway.calls) == 2
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["opencode-helper", "codex-helper"]
    assert "ReAct step" not in text
    assert "Action:" not in text
    assert "Verify HTML: did not complete successfully" in text
    assert "Fix HTML behavior" in text
    assert "thought" not in text
    assert "chain_of_thought" not in text


async def test_orchestrator_react_rejects_add_task_outside_allowed_agents() -> None:
    verify = FakeSubAdapter(
        "opencode-helper",
        [
            StreamChunk(
                event_type="error",
                error_code="verification_failed",
                error="needs design",
            )
        ],
    )
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"add_task","task":{'
                '"task_id":"design","agent_id":"outside-agent",'
                '"title":"Design","instruction":"Design UI","priority":2}}],'
                '"summary":"add designer"}'
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [_task("verify", "opencode-helper", "Verify", "Verify output")],
            "managed_agent_ids": ["opencode-helper"],
            "sub_adapters": {"opencode-helper": verify},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "Verify: did not complete successfully" in text
    assert "unknown agent_id 'outside-agent'" not in text
    assert not any(chunk.to_agent == "outside-agent" for chunk in chunks)


async def test_orchestrator_react_cannot_update_succeeded_task() -> None:
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"update_task","task_id":"task-a",'
                '"patch":{"instruction":"mutated"}}],"summary":"bad update"}'
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "Done", "Original")],
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "Done" in text
    assert "cannot update completed task" not in text
    assert adapter.received_messages[-1].content == "Original"


async def test_orchestrator_react_skip_task_prevents_execution() -> None:
    first = FakeSubAdapter("agent-a", _text_chunks("first done"))
    skipped = FakeSubAdapter("agent-b", _text_chunks("should not run"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"skip_task","task_id":"task-b",'
                '"reason":"not needed"},{"type":"finish","reason":"done"}],'
                '"summary":"skip second"}'
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [
                _task("task-a", "agent-a", "First", "Run first", priority=1),
                _task("task-b", "agent-b", "Second", "Run second", priority=2),
            ],
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": first, "agent-b": skipped},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a"]
    assert skipped.received_messages == []
    assert "Second: skipped because an earlier step did not complete" in text


async def test_orchestrator_react_empty_decision_continues_existing_tasks() -> None:
    first = FakeSubAdapter("agent-a", _text_chunks("first done"))
    second = FakeSubAdapter("agent-b", _text_chunks("second done"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(""),
            _react_decision_chunks('{"actions":[{"type":"finish","reason":"done"}]}'),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [
                _task("task-a", "agent-a", "First", "Run first", priority=1),
                _task(
                    "task-b",
                    "agent-b",
                    "Second",
                    "Run second",
                    priority=2,
                    depends_on=["task-a"],
                ),
            ],
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": first, "agent-b": second},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert "continuing existing task graph" not in text
    assert "- First" in text
    assert "- Second" in text
    assert "pending" not in text


async def test_orchestrator_react_max_iterations_stops_without_replanner() -> None:
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    react_gateway = SequencedGateway(
        [_react_decision_chunks('{"actions":[{"type":"finish"}],"summary":"unused"}')]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "max_iterations": 1,
            "tasks": [_task("task-a", "agent-a", "One", "Run one")],
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert react_gateway.calls == []
    assert "max_iterations reached (1)" not in text
    assert "- One" in text


async def test_orchestrator_react_added_task_receives_previous_results() -> None:
    first = FakeSubAdapter("agent-a", _text_chunks("Analysis result"))
    second = FakeSubAdapter("agent-b", _text_chunks("Follow-up result"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"add_task","task":{'
                '"task_id":"follow-up","agent_id":"agent-b",'
                '"title":"Follow up","instruction":"Use prior result.",'
                '"depends_on":["task-a"],"priority":2}}],'
                '"summary":"add follow-up"}'
            ),
            _react_decision_chunks('{"actions":[{"type":"finish","reason":"done"}]}'),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "Analyze", "Analyze request", priority=1)],
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": first, "agent-b": second},
        },
    )

    system_messages = [
        message for message in second.received_messages if message.role == "system"
    ]
    assert chunks[-1].event_type == "done"
    assert len(system_messages) == 1
    assert "Previous sub-agent results" in system_messages[0].content
    assert "task-a @agent-a succeeded" in system_messages[0].content
    assert "Analysis result" in system_messages[0].content


async def test_orchestrator_react_trace_can_be_hidden() -> None:
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    react_gateway = SequencedGateway(
        [_react_decision_chunks('{"actions":[{"type":"finish","reason":"done"}]}')]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_trace_visible": False,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "One", "Run one")],
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert len(react_gateway.calls) == 1
    assert "ReAct step" not in text
    assert "- One" in text
