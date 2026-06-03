"""Stream remapping helpers for Orchestrator sub-agent output."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable
from pathlib import Path

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator.types import SubTask, TaskAttempt, TaskState
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

TextBlock = Callable[..., Iterable[StreamChunk]]
FailureText = Callable[[SubTask, str, str | None], str]
ErrorReason = Callable[[StreamChunk], str]
AccumulateText = Callable[[TaskAttempt, StreamChunk], None]
AccumulateTool = Callable[[TaskAttempt, StreamChunk], None]


async def remapped_sub_stream(
    sub_adapter: BaseAgentAdapter,
    task: SubTask,
    agent_id: str,
    call_id_prefix: str,
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    attempt: TaskAttempt,
    *,
    text_block: TextBlock,
    failure_text: FailureText,
    error_reason: ErrorReason,
    accumulate_text_event: AccumulateText,
    accumulate_tool_event: AccumulateTool,
) -> AsyncIterator[tuple[StreamChunk, int, bool]]:
    index_map: dict[int, int] = {}
    open_block_index: int | None = None
    try:
        async for chunk in sub_adapter.stream(
            messages,
            system_prompt=None,
            config=None,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
        ):
            if chunk.event_type in {"start", "done"}:
                continue
            if chunk.event_type == "error":
                if open_block_index is not None:
                    yield StreamChunk(
                        event_type="block_end",
                        block_index=open_block_index,
                        agent_id=agent_id,
                    ), next_block_index, False
                    open_block_index = None
                attempt.error = error_reason(chunk)
                attempt.state = TaskState.FAILED
                text = failure_text(task, attempt.error, agent_id)
                for failure_chunk in text_block(
                    next_block_index,
                    text,
                    agent_id=agent_id,
                ):
                    yield failure_chunk, next_block_index + 1, True
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                accumulate_tool_event(attempt, chunk)
                remapped = remap_tool_call_id(chunk, call_id_prefix)
                yield attach_agent_id(remapped, agent_id), next_block_index, False
                continue
            if chunk.event_type == "heartbeat":
                yield attach_agent_id(chunk, agent_id), next_block_index, False
                continue
            if chunk.event_type not in {"block_start", "delta", "block_end"}:
                continue
            accumulate_text_event(attempt, chunk)
            remapped, next_block_index = remap_block_index(
                chunk,
                index_map,
                next_block_index,
            )
            if remapped.event_type == "block_start":
                open_block_index = remapped.block_index
            elif remapped.event_type == "block_end":
                open_block_index = None
            yield attach_agent_id(remapped, agent_id), next_block_index, False
    except Exception as exc:
        if open_block_index is not None:
            yield StreamChunk(
                event_type="block_end",
                block_index=open_block_index,
                agent_id=agent_id,
            ), next_block_index, False
            open_block_index = None
        attempt.error = str(exc)
        attempt.state = TaskState.FAILED
        text = failure_text(task, str(exc), agent_id)
        for failure_chunk in text_block(
            next_block_index,
            text,
            agent_id=agent_id,
        ):
            yield failure_chunk, next_block_index + 1, True
        return


def remap_block_index(
    chunk: StreamChunk,
    index_map: dict[int, int],
    next_block_index: int,
) -> tuple[StreamChunk, int]:
    if chunk.block_index is None:
        return chunk, next_block_index

    mapped_index = index_map.get(chunk.block_index)
    if mapped_index is None:
        mapped_index = next_block_index
        index_map[chunk.block_index] = mapped_index
        next_block_index += 1
    return chunk.model_copy(update={"block_index": mapped_index}), next_block_index


def remap_tool_call_id(chunk: StreamChunk, task_id: str) -> StreamChunk:
    if not chunk.call_id:
        return chunk
    return chunk.model_copy(update={"call_id": f"{task_id}.{chunk.call_id}"})


def attach_agent_id(chunk: StreamChunk, agent_id: str) -> StreamChunk:
    if chunk.agent_id == agent_id:
        return chunk
    return chunk.model_copy(update={"agent_id": agent_id})
