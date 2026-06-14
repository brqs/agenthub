"""Shared pre-runtime shortcuts for external agent adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.external.direct_chat import DirectChatDecision
from app.agents.external.workspace_prompt import (
    direct_identity_response,
    direct_small_talk_response,
)
from app.agents.requirement_alignment import maybe_handle_single_agent_requirement_alignment
from app.agents.types import ChatMessage, StreamChunk

ErrorChunkFactory = Callable[[str, str], StreamChunk]
DirectChatFn = Callable[..., Awaitable[DirectChatDecision]]


@dataclass(frozen=True)
class RuntimePreludeResult:
    merged_config: dict[str, Any]
    stream: AsyncIterator[StreamChunk] | None = None
    messages: list[ChatMessage] | None = None
    leading_chunks: tuple[StreamChunk, ...] = ()

    @property
    def handled(self) -> bool:
        return self.stream is not None


async def external_runtime_prelude(
    *,
    adapter: Any,
    provider: str,
    messages: list[ChatMessage],
    system_prompt: str | None,
    config: dict[str, Any] | None,
    workspace_path: Path | None,
    workspace_error: str,
    error_chunk: ErrorChunkFactory,
    direct_chat: DirectChatFn,
) -> RuntimePreludeResult:
    if workspace_path is None:
        return RuntimePreludeResult(
            merged_config={},
            stream=_iter_chunks([error_chunk("workspace_violation", workspace_error)]),
        )

    merged = adapter.merged_config(config)
    if _must_use_runtime_for_orchestrator_task(merged):
        return RuntimePreludeResult(merged_config=merged)

    alignment = await maybe_handle_single_agent_requirement_alignment(
        agent_id=adapter.agent_id,
        messages=messages,
        config=merged,
        workspace_path=workspace_path,
    )
    if alignment.handled and alignment.stream is not None:
        return RuntimePreludeResult(merged_config=merged, stream=alignment.stream)
    if alignment.messages is not None:
        messages = alignment.messages
    leading_chunks = alignment.leading_chunks

    direct_response = direct_identity_response(messages, agent_id=adapter.agent_id)
    if direct_response:
        block_offset = leading_block_count(leading_chunks)
        return RuntimePreludeResult(
            merged_config=merged,
            stream=_iter_chunks(
                [
                    *leading_chunks,
                    *text_result_chunks(
                        direct_response,
                        adapter.agent_id,
                        block_index=block_offset,
                    ),
                ]
            ),
        )

    direct_response = direct_small_talk_response(messages, agent_id=adapter.agent_id)
    if direct_response:
        block_offset = leading_block_count(leading_chunks)
        return RuntimePreludeResult(
            merged_config=merged,
            stream=_iter_chunks(
                [
                    *leading_chunks,
                    *text_result_chunks(
                        direct_response,
                        adapter.agent_id,
                        block_index=block_offset,
                    ),
                ]
            ),
        )

    route = await direct_chat(
        agent_id=adapter.agent_id,
        provider=provider,
        messages=messages,
        system_prompt=adapter.effective_system_prompt(system_prompt),
        config=merged,
    )
    if route.route == "direct_chat" and route.stream is not None:
        if leading_chunks:
            return RuntimePreludeResult(
                merged_config=merged,
                stream=_chain_chunks_stream(leading_chunks, route.stream),
            )
        return RuntimePreludeResult(merged_config=merged, stream=route.stream)
    return RuntimePreludeResult(
        merged_config=merged,
        messages=messages,
        leading_chunks=leading_chunks,
    )


def _must_use_runtime_for_orchestrator_task(config: dict[str, Any]) -> bool:
    runtime_context = config.get("runtime_context")
    if not isinstance(runtime_context, dict):
        return False
    if not runtime_context.get("orchestrator_task_id"):
        return False
    task_type = str(runtime_context.get("orchestrator_task_type") or "").strip()
    return task_type not in {"conversation", "dialogue_turn"}


def text_result_chunks(
    text: str,
    agent_id: str,
    *,
    block_index: int = 0,
) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="block_start", block_index=block_index, block_type="text"),
        StreamChunk(event_type="delta", block_index=block_index, text_delta=text),
        StreamChunk(event_type="block_end", block_index=block_index),
        StreamChunk(event_type="done", agent_id=agent_id, total_blocks=block_index + 1),
    ]


def leading_block_count(chunks: tuple[StreamChunk, ...]) -> int:
    return sum(1 for chunk in chunks if chunk.event_type == "block_start")


def offset_stream_chunk_indices(chunk: StreamChunk, block_offset: int) -> StreamChunk:
    if block_offset <= 0:
        return chunk
    update: dict[str, Any] = {}
    if chunk.block_index is not None:
        update["block_index"] = chunk.block_index + block_offset
    if chunk.total_blocks is not None:
        update["total_blocks"] = chunk.total_blocks + block_offset
    return chunk.model_copy(update=update) if update else chunk


async def _iter_chunks(chunks: list[StreamChunk]) -> AsyncIterator[StreamChunk]:
    for chunk in chunks:
        yield chunk


async def _chain_chunks_stream(
    chunks: tuple[StreamChunk, ...],
    stream: AsyncIterator[StreamChunk],
) -> AsyncIterator[StreamChunk]:
    block_offset = leading_block_count(chunks)
    for chunk in chunks:
        yield chunk
    async for chunk in stream:
        yield offset_stream_chunk_indices(chunk, block_offset)
