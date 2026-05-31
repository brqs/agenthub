"""SSE stream endpoint — Owner: B1.

This is the ★ critical integration point ★ between B1 (routing/persistence) and
B2 (Agent layer). B1 calls `agents.registry.get_adapter()` and pipes the
resulting AsyncIterator[StreamChunk] into SSE events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.registry import AgentNotFoundError, get_adapter
from app.agents.types import StreamChunk
from app.api.v1.conversations import _get_owned_conversation
from app.api.v1.stream_accumulator import StreamContentAccumulator
from app.api.v1.stream_orchestrator_context import (
    apply_orchestrator_stream_context,
    cancel_orchestrator_run,
)
from app.api.v1.stream_preview import maybe_autostart_platform_preview
from app.core.deps import DbSession, get_current_user
from app.models.message import Message
from app.models.user import User
from app.services.context_builder import build_context
from app.services.workspace_service import WorkspaceService

router = APIRouter()

_ContentAccumulator = StreamContentAccumulator


async def _event_generator(
    db: AsyncSession,
    request: Request,
    message: Message,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-formatted events for a pending agent message."""
    accumulator = _ContentAccumulator()
    try:
        if not message.agent_id:
            message.status = "error"
            await db.commit()
            yield StreamChunk(
                event_type="error",
                error_code="missing_agent",
                error="Message has no agent_id",
            ).to_sse()
            return

        adapter = await get_adapter(message.agent_id, db)
        history = await build_context(db, message.conversation_id)
        workspace = await WorkspaceService().get_or_create(db, message.conversation_id)
        history, stream_config = await apply_orchestrator_stream_context(
            db,
            message,
            adapter,
            history,
        )

        # Mark streaming
        message.status = "streaming"
        await db.commit()

        disconnected = False
        final_done: StreamChunk | None = None
        next_block_index = 0
        async for chunk in adapter.stream(
            history,
            config=stream_config,
            workspace_path=Path(workspace.root_path),
            tool_specs=None,
        ):
            if chunk.block_index is not None:
                next_block_index = max(next_block_index, chunk.block_index + 1)
            if chunk.event_type == "done":
                final_done = chunk
                if chunk.total_blocks is not None:
                    next_block_index = max(next_block_index, chunk.total_blocks)
                break
            if await request.is_disconnected():
                disconnected = True
                break
            accumulator_error = accumulator.feed(chunk)
            if accumulator_error is not None:
                message.content = accumulator.to_list()
                message.status = "error"
                await db.commit()
                yield accumulator_error.to_sse()
                return
            yield chunk.to_sse()
            if chunk.event_type == "error":
                message.content = accumulator.to_list()
                message.status = "error"
                await db.commit()
                return

        # Persist
        if disconnected:
            await cancel_orchestrator_run(stream_config)
        elif final_done is not None:
            preview_chunks, next_block_index = await maybe_autostart_platform_preview(
                db=db,
                message=message,
                history=history,
                workspace_path=Path(workspace.root_path),
                block_index=next_block_index,
                existing_blocks=accumulator.to_list(),
            )
            for preview_chunk in preview_chunks:
                accumulator_error = accumulator.feed(preview_chunk)
                if accumulator_error is not None:
                    message.content = accumulator.to_list()
                    message.status = "error"
                    await db.commit()
                    yield accumulator_error.to_sse()
                    return
                yield preview_chunk.to_sse()
            yield final_done.model_copy(update={"total_blocks": next_block_index}).to_sse()
        has_orphaned_tool_call = accumulator.finalize_orphaned_tools()
        message.content = accumulator.to_list()
        message.status = "error" if disconnected or has_orphaned_tool_call else "done"
        await db.commit()
    except AgentNotFoundError as e:
        message.status = "error"
        await db.commit()
        yield StreamChunk(
            event_type="error", error_code="agent_not_found", error=str(e)
        ).to_sse()
    except Exception as e:  # noqa: BLE001
        message.content = accumulator.to_list()
        message.status = "error"
        await db.commit()
        yield StreamChunk(
            event_type="error", error_code="internal_error", error=str(e)
        ).to_sse()


@router.get("/messages/{msg_id}/stream")
async def stream_message(
    msg_id: UUID,
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> EventSourceResponse:
    """SSE stream for an agent message."""
    message = await db.get(Message, msg_id)
    if not message:
        raise HTTPException(
            404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )

    # Ownership check via parent conversation
    await _get_owned_conversation(db, user.id, message.conversation_id)

    if message.role != "agent":
        raise HTTPException(
            400,
            detail={
                "error": {
                    "code": "NOT_AGENT_MESSAGE",
                    "message": "Only agent messages can be streamed",
                }
            },
        )

    return EventSourceResponse(_event_generator(db, request, message))
