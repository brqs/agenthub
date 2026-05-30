"""Shared SDK event stream folding for external runtime adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable
from typing import Any

from app.agents.external.runtime_budget import (
    RuntimeBudget,
    RuntimeBudgetConfig,
    RuntimeTimeoutError,
    iter_with_runtime_budget,
)
from app.agents.runtime_guard import PreviewDeployTextFilter
from app.agents.types import StreamChunk

MapSdkEvent = Callable[[Any], Iterable[StreamChunk]]
TimeoutErrorChunk = Callable[[RuntimeTimeoutError], StreamChunk]
ExceptionStream = Callable[[BaseException, bool], AsyncIterator[StreamChunk]]


async def stream_sdk_events(
    sdk_stream: AsyncIterator[Any],
    *,
    budget_config: RuntimeBudgetConfig,
    agent_id: str,
    provider: str,
    map_event: MapSdkEvent,
    timeout_error_chunk: TimeoutErrorChunk,
    exception_stream: ExceptionStream,
) -> AsyncIterator[StreamChunk]:
    block_open = False
    block_index = 0
    total_blocks = 0
    saw_runtime_chunk = False
    text_filter = PreviewDeployTextFilter()

    async def flush_text(*, close_block: bool) -> AsyncIterator[StreamChunk]:
        nonlocal block_open, block_index, total_blocks
        pending_text = text_filter.flush()
        if pending_text:
            if not block_open:
                yield StreamChunk(
                    event_type="block_start",
                    block_index=block_index,
                    block_type="text",
                )
                block_open = True
            yield StreamChunk(
                event_type="delta",
                block_index=block_index,
                text_delta=pending_text,
            )
        if close_block and block_open:
            yield StreamChunk(event_type="block_end", block_index=block_index)
            total_blocks += 1
            block_index += 1
            block_open = False

    try:
        budget = RuntimeBudget(budget_config)
        async for sdk_event in iter_with_runtime_budget(
            sdk_stream,
            budget,
            agent_id=agent_id,
            provider=provider,
        ):
            if isinstance(sdk_event, StreamChunk) and sdk_event.event_type == "heartbeat":
                yield sdk_event
                continue
            for chunk in map_event(sdk_event):
                saw_runtime_chunk = True
                if chunk.event_type == "delta":
                    text = text_filter.feed(chunk.text_delta or "")
                    if not text:
                        continue
                    if not block_open:
                        yield StreamChunk(
                            event_type="block_start",
                            block_index=block_index,
                            block_type="text",
                        )
                        block_open = True
                    chunk.block_index = block_index
                    chunk.text_delta = text
                    yield chunk
                    continue

                async for pending_chunk in flush_text(close_block=True):
                    yield pending_chunk
                yield chunk
    except RuntimeTimeoutError as exc:
        async for pending_chunk in flush_text(close_block=True):
            yield pending_chunk
        yield timeout_error_chunk(exc)
        return
    except Exception as exc:  # noqa: BLE001
        async for pending_chunk in flush_text(close_block=True):
            yield pending_chunk
        async for chunk in exception_stream(exc, saw_runtime_chunk):
            yield chunk
        return

    async for pending_chunk in flush_text(close_block=True):
        yield pending_chunk

    yield StreamChunk(
        event_type="done",
        agent_id=agent_id,
        total_blocks=total_blocks,
    )
