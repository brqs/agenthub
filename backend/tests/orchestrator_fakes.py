"""Shared OrchestratorAdapter test fakes and helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


async def _collect(
    adapter: OrchestratorAdapter,
    config: dict[str, Any] | None = None,
    messages: list[ChatMessage] | None = None,
    workspace_path: Path | None = None,
) -> list[StreamChunk]:
    stream_config = dict(config or {})
    stream_config.setdefault("orchestrator_subagent_text_visible", True)
    return [
        chunk
        async for chunk in adapter.stream(
            messages=messages or [ChatMessage(role="user", content="Build a todo app")],
            config=stream_config,
            workspace_path=workspace_path,
        )
    ]


def _assert_blocks_balanced(chunks: list[StreamChunk]) -> None:
    stack: list[int] = []
    for chunk in chunks:
        if chunk.event_type == "block_start" and chunk.block_index is not None:
            stack.append(chunk.block_index)
        elif chunk.event_type == "block_end" and chunk.block_index is not None:
            assert stack, f"Unexpected block_end for block_index={chunk.block_index}"
            assert (
                stack.pop() == chunk.block_index
            ), f"Mismatched block_end for block_index={chunk.block_index}"
    assert not stack, f"Unclosed blocks: {stack}"


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
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        self.received_config = config
        for chunk in self._chunks:
            yield chunk


class FakePartialThenExceptionAdapter(BaseAgentAdapter):
    """Yields some chunks then raises an exception mid-stream."""

    provider = "fake"

    def __init__(self, agent_id: str, chunks: list[StreamChunk], exc: Exception) -> None:
        super().__init__(agent_id=agent_id)
        self._chunks = chunks
        self._exc = exc

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        for chunk in self._chunks:
            yield chunk
        raise self._exc


class FakeWorkspaceWriterAdapter(FakeSubAdapter):
    def __init__(
        self,
        agent_id: str,
        chunks: list[StreamChunk],
        write_path: str,
        content: str = "ok",
    ) -> None:
        super().__init__(agent_id, chunks)
        self.write_path = write_path
        self.content = content

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if workspace_path is not None:
            target = workspace_path / self.write_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.content, encoding="utf-8")
        async for chunk in super().stream(
            messages,
            system_prompt=system_prompt,
            config=config,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
        ):
            yield chunk


class FakeWorkspaceVerifierAdapter(FakeSubAdapter):
    def __init__(self, agent_id: str, verify_path: str) -> None:
        super().__init__(agent_id, [])
        self.verify_path = verify_path
        self.verified_content = ""

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        self.received_config = config
        target = workspace_path / self.verify_path if workspace_path else None
        self.verified_content = target.read_text(encoding="utf-8") if target else ""
        checks = {
            "title": "Orchestrator Flow Smoke Test" in self.verified_content,
            "input": "<input" in self.verified_content,
            "button": "<button" in self.verified_content,
            "display": "textContent" in self.verified_content,
        }
        result = (
            f"Checked {self.verify_path}: "
            f"title={checks['title']}, input={checks['input']}, "
            f"button={checks['button']}, display={checks['display']}"
        )
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(
            event_type="tool_call",
            call_id="verify-1",
            tool_name="read_file",
            tool_arguments={"path": self.verify_path},
        )
        yield StreamChunk(
            event_type="tool_result",
            call_id="verify-1",
            tool_status="ok" if all(checks.values()) else "error",
            tool_output=result,
        )
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta=result)
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)


class FakePlannerGateway:
    def __init__(self, chunks: list[StreamChunk]) -> None:
        self._chunks = chunks
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
        for chunk in self._chunks:
            yield chunk


class FakeAnswerGateway(FakePlannerGateway):
    pass


class SequencedGateway:
    def __init__(self, chunk_sequences: list[list[StreamChunk]]) -> None:
        self._chunk_sequences = chunk_sequences
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
        index = len(self.calls) - 1
        chunks = self._chunk_sequences[index] if index < len(self._chunk_sequences) else []
        for chunk in chunks:
            yield chunk


def _react_decision_chunks(payload: str) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="react"),
        StreamChunk(event_type="delta", text_delta=payload),
        StreamChunk(event_type="done", agent_id="react"),
    ]


def _task(
    task_id: str,
    agent_id: str,
    title: str,
    instruction: str,
    priority: int = 0,
    depends_on: list[str] | None = None,
    expected_output: str | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    task = {
        "task_id": task_id,
        "agent_id": agent_id,
        "title": title,
        "instruction": instruction,
        "depends_on": depends_on or [],
        "priority": priority,
        "include_history": include_history,
    }
    if expected_output is not None:
        task["expected_output"] = expected_output
    return task


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
