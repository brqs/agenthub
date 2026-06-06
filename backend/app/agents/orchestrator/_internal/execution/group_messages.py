"""Helpers for optional per-agent group chat messages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.types import StreamChunk


def group_messages_enabled(config: Mapping[str, Any]) -> bool:
    return (
        config.get("orchestrator_group_messages_enabled", True) is not False
        and config.get("orchestrator_group_message_writer") is not None
    )


async def start_group_message(
    config: Mapping[str, Any],
    *,
    agent_id: str,
) -> tuple[str | None, StreamChunk | None]:
    writer = config.get("orchestrator_group_message_writer")
    start = getattr(writer, "start_message", None)
    if not callable(start):
        return None, None
    try:
        chunk = await start(agent_id=agent_id)
    except Exception:  # noqa: BLE001
        return None, None
    return chunk.message_id, chunk


async def finish_group_message(
    config: Mapping[str, Any],
    message_id: str | None,
    *,
    status: str = "done",
    error: str | None = None,
    error_code: str | None = None,
) -> StreamChunk | None:
    if not message_id:
        return None
    writer = config.get("orchestrator_group_message_writer")
    finish = getattr(writer, "finish_message", None)
    if not callable(finish):
        return None
    try:
        chunk = await finish(
            message_id,
            status=status,
            error=error,
            error_code=error_code,
        )
    except Exception:  # noqa: BLE001
        return None
    return chunk if isinstance(chunk, StreamChunk) else None


def child_message_chunk(
    chunk: StreamChunk,
    *,
    message_id: str,
    agent_id: str,
) -> StreamChunk:
    update: dict[str, Any] = {"message_id": message_id}
    if not chunk.agent_id:
        update["agent_id"] = agent_id
    return chunk.model_copy(update=update)
