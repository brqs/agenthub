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
from app.agents.types import ChatMessage, StreamChunk

ErrorChunkFactory = Callable[[str, str], StreamChunk]
DirectChatFn = Callable[..., Awaitable[DirectChatDecision]]


@dataclass(frozen=True)
class RuntimePreludeResult:
    merged_config: dict[str, Any]
    stream: AsyncIterator[StreamChunk] | None = None

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

    direct_response = direct_identity_response(messages, agent_id=adapter.agent_id)
    if direct_response:
        return RuntimePreludeResult(
            merged_config=merged,
            stream=_iter_chunks(text_result_chunks(direct_response, adapter.agent_id)),
        )

    direct_response = direct_small_talk_response(messages, agent_id=adapter.agent_id)
    if direct_response:
        return RuntimePreludeResult(
            merged_config=merged,
            stream=_iter_chunks(text_result_chunks(direct_response, adapter.agent_id)),
        )

    route = await direct_chat(
        agent_id=adapter.agent_id,
        provider=provider,
        messages=messages,
        system_prompt=adapter.effective_system_prompt(system_prompt),
        config=merged,
    )
    if route.route == "direct_chat" and route.stream is not None:
        return RuntimePreludeResult(merged_config=merged, stream=route.stream)
    return RuntimePreludeResult(merged_config=merged)


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
        StreamChunk(event_type="done", agent_id=agent_id, total_blocks=1),
    ]


async def _iter_chunks(chunks: list[StreamChunk]) -> AsyncIterator[StreamChunk]:
    for chunk in chunks:
        yield chunk
