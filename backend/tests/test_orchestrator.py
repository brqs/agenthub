"""Tests for OrchestratorAdapter injection-based dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.types import ChatMessage, StreamChunk


async def _collect(
    adapter: OrchestratorAdapter,
    config: dict[str, Any] | None = None,
    messages: list[ChatMessage] | None = None,
) -> list[StreamChunk]:
    return [
        chunk
        async for chunk in adapter.stream(
            messages=messages or [ChatMessage(role="user", content="Build a todo app")],
            config=config,
        )
    ]


class FakeSubAdapter(BaseAgentAdapter):
    provider = "fake"

    def __init__(
        self,
        agent_id: str,
        chunks: list[StreamChunk],
        system_prompt: str | None = "fake prompt",
    ) -> None:
        super().__init__(agent_id=agent_id, system_prompt=system_prompt)
        self._chunks = chunks
        self.received_messages: list[ChatMessage] = []
        self.received_system_prompt: str | None = None
        self.received_config: dict[str, Any] | None = None

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        self.received_config = config
        for chunk in self._chunks:
            yield chunk


def _task(
    task_id: str,
    agent_id: str,
    title: str,
    instruction: str,
    priority: int = 0,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "title": title,
        "instruction": instruction,
        "depends_on": depends_on or [],
        "priority": priority,
    }


def _text_chunks(text: str, block_index: int = 0) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="sub-agent"),
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
        ),
        StreamChunk(event_type="delta", block_index=block_index, text_delta=text),
        StreamChunk(event_type="block_end", block_index=block_index),
        StreamChunk(event_type="done", agent_id="sub-agent", total_blocks=1),
    ]


async def test_orchestrator_emits_planning_agent_switch_subagent_and_summary() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("backend done"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("frontend done"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-b", "agent-b", "Frontend UI", "Build UI", priority=2),
                _task("task-a", "agent-a", "Backend API", "Build API", priority=1),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[0].event_type == "start"
    assert chunks[-1].event_type == "done"
    assert [chunk.event_type for chunk in chunks].count("start") == 1
    assert [chunk.event_type for chunk in chunks].count("done") == 1
    assert any(
        chunk.event_type == "delta" and "Planned 2 sub-task(s)" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert [
        (chunk.from_agent, chunk.to_agent, chunk.task)
        for chunk in chunks
        if chunk.event_type == "agent_switch"
    ] == [
        ("orchestrator", "agent-a", "Backend API"),
        ("orchestrator", "agent-b", "Frontend UI"),
    ]
    assert any(chunk.text_delta == "backend done" for chunk in chunks)
    assert any(chunk.text_delta == "frontend done" for chunk in chunks)
    assert any("Execution summary" in (chunk.text_delta or "") for chunk in chunks)


async def test_orchestrator_remaps_block_indices_without_collisions() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a", block_index=0))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b", block_index=0))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    block_starts = [
        chunk.block_index for chunk in chunks if chunk.event_type == "block_start"
    ]
    assert block_starts == list(range(len(block_starts)))

    started = set(block_starts)
    for chunk in chunks:
        if chunk.event_type in {"delta", "block_end"} and chunk.block_index is not None:
            assert chunk.block_index in started

    a_delta = next(chunk for chunk in chunks if chunk.text_delta == "from a")
    b_delta = next(chunk for chunk in chunks if chunk.text_delta == "from b")
    assert a_delta.block_index != b_delta.block_index


async def test_orchestrator_preserves_subagent_metadata_and_delta_fields() -> None:
    sub_chunks = [
        StreamChunk(event_type="start", agent_id="agent-a"),
        StreamChunk(
            event_type="block_start",
            block_index=3,
            block_type="code",
            metadata={"language": "python", "filename": "app.py"},
        ),
        StreamChunk(event_type="delta", block_index=3, code_delta="print('ok')\n"),
        StreamChunk(event_type="block_end", block_index=3),
        StreamChunk(event_type="block_start", block_index=7, block_type="text"),
        StreamChunk(event_type="delta", block_index=7, text_delta="notes"),
        StreamChunk(event_type="block_end", block_index=7),
        StreamChunk(event_type="done", agent_id="agent-a", total_blocks=2),
    ]
    adapter_a = FakeSubAdapter("agent-a", sub_chunks)
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Code", "Write code")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    code_start = next(chunk for chunk in chunks if chunk.block_type == "code")
    code_delta = next(chunk for chunk in chunks if chunk.code_delta is not None)
    text_delta = next(chunk for chunk in chunks if chunk.text_delta == "notes")

    assert code_start.metadata == {"language": "python", "filename": "app.py"}
    assert code_delta.code_delta == "print('ok')\n"
    assert code_delta.block_index == code_start.block_index
    assert text_delta.block_index != code_start.block_index


async def test_orchestrator_does_not_require_database() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("factory result"))
    factory_calls: list[str] = []

    async def adapter_factory(agent_id: str) -> BaseAgentAdapter:
        factory_calls.append(agent_id)
        return adapter_a

    messages = [ChatMessage(role="user", content="Initial request")]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Injected task")],
            "adapter_factory": adapter_factory,
        },
    )

    assert chunks[-1].event_type == "done"
    assert factory_calls == ["agent-a"]
    assert adapter_a.received_messages == [
        ChatMessage(role="user", content="Initial request"),
        ChatMessage(role="user", content="Injected task"),
    ]
    assert adapter_a.received_system_prompt is None
    assert adapter_a.received_config is None


async def test_orchestrator_requires_task_plan_or_emits_clear_error() -> None:
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    missing_tasks = await _collect(orchestrator, config={"sub_adapters": {}})
    assert [chunk.event_type for chunk in missing_tasks] == ["start", "error"]
    assert missing_tasks[1].error_code == "missing_task_plan"

    missing_adapters = await _collect(
        orchestrator,
        config={"tasks": [_task("task-a", "agent-a", "Backend API", "Build API")]},
    )
    assert [chunk.event_type for chunk in missing_adapters] == ["start", "error"]
    assert missing_adapters[1].error_code == "missing_sub_adapters"


async def test_orchestrator_intercepts_subagent_error_chunk() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Build API")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and "@agent-a failed: too many requests" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any("- failed: @agent-a - Backend API" in (chunk.text_delta or "") for chunk in chunks)
