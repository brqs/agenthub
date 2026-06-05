"""SSE stream endpoint — Owner: B1.

This is the ★ critical integration point ★ between B1 (routing/persistence) and
B2 (Agent layer). B1 calls `agents.registry.get_adapter()` and pipes the
resulting AsyncIterator[StreamChunk] into SSE events.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
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
from app.core.config import settings
from app.core.database import SessionFactory
from app.core.deps import DbSession, get_current_user
from app.models.message import Message
from app.models.user import User
from app.services.context_builder import build_context
from app.services.message_lifecycle import cleanup_stale_streaming_messages
from app.services.workspace_service import WorkspaceService
from app.services.workspace_workflow_runtime import WorkspaceWorkflowRuntimeService

router = APIRouter()

_ContentAccumulator = StreamContentAccumulator
workflow_runtime_service = WorkspaceWorkflowRuntimeService()


@dataclass
class StreamRunSession:
    message_id: UUID
    conversation_id: UUID
    events: list[dict[str, str]] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    terminal: bool = False
    task: asyncio.Task[None] | None = None


class StreamRunManager:
    """In-process owner for agent runtime tasks, shared by SSE subscribers."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, StreamRunSession] = {}
        self._lock = asyncio.Lock()

    async def get(self, message_id: UUID) -> StreamRunSession | None:
        async with self._lock:
            return self._sessions.get(message_id)

    async def start(self, message: Message) -> StreamRunSession:
        async with self._lock:
            existing = self._sessions.get(message.id)
            if existing is not None:
                return existing
            session = StreamRunSession(
                message_id=message.id,
                conversation_id=message.conversation_id,
            )
            session.task = asyncio.create_task(self._run(session))
            self._sessions[message.id] = session
            return session

    async def publish(
        self,
        session: StreamRunSession,
        event: dict[str, str],
    ) -> None:
        async with session.condition:
            session.events.append(event)
            session.condition.notify_all()

    async def subscribe(
        self,
        session: StreamRunSession,
    ) -> AsyncIterator[dict[str, str]]:
        index = 0
        while True:
            async with session.condition:
                while index >= len(session.events) and not session.terminal:
                    await session.condition.wait()
                if index < len(session.events):
                    event = session.events[index]
                    index += 1
                else:
                    return
            yield event

    async def terminalize(self, session: StreamRunSession) -> None:
        async with session.condition:
            session.terminal = True
            session.condition.notify_all()

    async def _run(self, session: StreamRunSession) -> None:
        try:
            async with SessionFactory() as db:
                message = await db.get(Message, session.message_id)
                if message is None:
                    return
                async for event in _runtime_event_generator(db, message):
                    await self.publish(session, event)
        finally:
            await self.terminalize(session)
            async with self._lock:
                current = self._sessions.get(session.message_id)
                if current is session:
                    self._sessions.pop(session.message_id, None)


stream_run_manager = StreamRunManager()


class StreamDisconnectedError(RuntimeError):
    """Raised when the client disconnects while an adapter is still running."""


class StreamTimeoutError(RuntimeError):
    """Raised when an adapter stream exceeds the B1 stream budget."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


async def _wait_for_disconnect(request: Request) -> None:
    while not await _is_disconnected(request):
        await asyncio.sleep(0.5)


async def _is_disconnected(request: Request) -> bool:
    try:
        return await asyncio.wait_for(request.is_disconnected(), timeout=0.1)
    except TimeoutError:
        return False


async def _next_chunk_or_disconnect(
    iterator: AsyncIterator[StreamChunk],
    request: Request,
    *,
    timeout_seconds: float | None = None,
    timeout_error_code: str = "stream_timeout",
) -> StreamChunk:
    next_task: asyncio.Task[StreamChunk] = asyncio.create_task(
        _anext_stream_chunk(iterator)
    )
    disconnect_task = asyncio.create_task(_wait_for_disconnect(request))
    try:
        done, _ = await asyncio.wait(
            {next_task, disconnect_task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            await _cancel_task_with_budget(next_task)
            await _cancel_task_with_budget(disconnect_task)
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                with contextlib.suppress(BaseException):
                    await asyncio.wait_for(aclose(), timeout=0.5)
            raise StreamTimeoutError(
                timeout_error_code,
                "Agent stream timed out before the Agent finished.",
            )
        if disconnect_task in done:
            await _cancel_task_with_budget(next_task)
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                with contextlib.suppress(BaseException):
                    await asyncio.wait_for(aclose(), timeout=0.5)
            raise StreamDisconnectedError
        await _cancel_task_with_budget(disconnect_task)
        return next_task.result()
    finally:
        for task in (next_task, disconnect_task):
            if not task.done():
                task.cancel()


async def _next_chunk_with_timeout(
    iterator: AsyncIterator[StreamChunk],
    *,
    timeout_seconds: float | None = None,
    timeout_error_code: str = "stream_timeout",
) -> StreamChunk:
    next_task: asyncio.Task[StreamChunk] = asyncio.create_task(
        _anext_stream_chunk(iterator)
    )
    try:
        done, _ = await asyncio.wait(
            {next_task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            await _cancel_task_with_budget(next_task)
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                with contextlib.suppress(BaseException):
                    await asyncio.wait_for(aclose(), timeout=0.5)
            raise StreamTimeoutError(
                timeout_error_code,
                "Agent stream timed out before the Agent finished.",
            )
        return next_task.result()
    finally:
        if not next_task.done():
            next_task.cancel()


async def _anext_stream_chunk(iterator: AsyncIterator[StreamChunk]) -> StreamChunk:
    return await anext(iterator)


async def _cancel_task_with_budget(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    with contextlib.suppress(BaseException):
        await asyncio.wait_for(task, timeout=0.5)


async def _mark_stream_error(
    db: AsyncSession,
    message: Message,
    accumulator: _ContentAccumulator,
    text: str,
) -> None:
    message_id = message.id
    with contextlib.suppress(Exception):
        await db.rollback()
    refreshed = await db.get(Message, message_id)
    if refreshed is None:
        return
    accumulator.finalize_task_cards(success=False)
    content = accumulator.to_list()
    error_block = {"type": "text", "text": text}
    refreshed.content = [*content, error_block] if content else [error_block]
    refreshed.status = "error"
    message.status = "error"
    try:
        await db.commit()
    except Exception:
        await db.rollback()


async def _mark_orphaned_stream_error(db: AsyncSession, message: Message) -> None:
    message.status = "error"
    if not message.content:
        message.content = [
            {
                "type": "text",
                "text": "Agent stream was interrupted before completion. Please retry.",
            }
        ]
    await db.commit()


async def _single_sse_event(event: dict[str, str]) -> AsyncIterator[dict[str, str]]:
    yield event


def _stream_wait_budget(
    *,
    now: float,
    started_at: float,
    last_activity_at: float,
) -> tuple[float, str]:
    idle_remaining = settings.agent_stream_idle_timeout_seconds - (now - last_activity_at)
    hard_remaining = settings.agent_stream_hard_timeout_seconds - (now - started_at)
    if hard_remaining <= 0:
        return 0.0, "stream_hard_timeout"
    if idle_remaining <= 0:
        return 0.0, "stream_idle_timeout"
    if hard_remaining <= idle_remaining:
        return hard_remaining, "stream_hard_timeout"
    return idle_remaining, "stream_idle_timeout"


async def _event_generator(
    db: AsyncSession,
    request: Request,
    message: Message,
) -> AsyncIterator[dict[str, str]]:
    """Compatibility wrapper used by focused tests."""
    _ = request
    async for event in _runtime_event_generator(db, message):
        yield event


async def _runtime_event_generator(
    db: AsyncSession,
    message: Message,
) -> AsyncIterator[dict[str, str]]:
    """Run an agent message and yield SSE-formatted events."""
    accumulator = _ContentAccumulator()
    stream_claimed = False
    stream_config: dict[str, Any] | None = None
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
        history = await build_context(
            db,
            message.conversation_id,
            current_agent_id=message.agent_id,
        )
        workspace = await WorkspaceService().get_or_create(db, message.conversation_id)
        history, stream_config = await apply_orchestrator_stream_context(
            db,
            message,
            adapter,
            history,
        )

        stream_claimed = True

        final_done: StreamChunk | None = None
        next_block_index = 0
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        last_activity_at = started_at
        stream_config = {
            **(stream_config or {}),
            "runtime_context": {
                "conversation_id": str(message.conversation_id),
                "agent_message_id": str(message.id),
                "agent_id": message.agent_id,
            },
        }
        adapter_iterator = adapter.stream(
            history,
            config=stream_config,
            workspace_path=Path(workspace.root_path),
            tool_specs=None,
        ).__aiter__()
        while True:
            try:
                wait_timeout, timeout_code = _stream_wait_budget(
                    now=loop.time(),
                    started_at=started_at,
                    last_activity_at=last_activity_at,
                )
                chunk = await _next_chunk_with_timeout(
                    adapter_iterator,
                    timeout_seconds=wait_timeout,
                    timeout_error_code=timeout_code,
                )
            except StopAsyncIteration:
                break
            last_activity_at = loop.time()
            if chunk.block_index is not None:
                next_block_index = max(next_block_index, chunk.block_index + 1)
            if chunk.event_type == "done":
                final_done = chunk
                if chunk.total_blocks is not None:
                    next_block_index = max(next_block_index, chunk.total_blocks)
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
        if final_done is not None:
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
        accumulator.finalize_task_cards(success=not has_orphaned_tool_call)
        blocks = accumulator.to_list()
        if not has_orphaned_tool_call:
            blocks = await workflow_runtime_service.enrich_workflow_blocks(
                db,
                message.conversation_id,
                blocks,
            )
        message.content = blocks
        message.status = "error" if has_orphaned_tool_call else "done"
        await db.commit()
    except StreamTimeoutError as e:
        await cancel_orchestrator_run(stream_config)
        await _mark_stream_error(db, message, accumulator, str(e))
        yield StreamChunk(
            event_type="error",
            error_code=e.error_code,
            error=str(e),
        ).to_sse()
    except asyncio.CancelledError:
        await cancel_orchestrator_run(stream_config)
        await _mark_stream_error(
            db,
            message,
            accumulator,
            "Stream was cancelled before the Agent finished.",
        )
        raise
    except AgentNotFoundError as e:
        message.status = "error"
        await db.commit()
        yield StreamChunk(
            event_type="error", error_code="agent_not_found", error=str(e)
        ).to_sse()
    except Exception as e:  # noqa: BLE001
        await _mark_stream_error(db, message, accumulator, str(e))
        yield StreamChunk(
            event_type="error", error_code="internal_error", error=str(e)
        ).to_sse()
    finally:
        if stream_claimed and message.status in {"pending", "streaming"}:
            await cancel_orchestrator_run(stream_config)
            await _mark_stream_error(
                db,
                message,
                accumulator,
                "Agent stream ended before a final done or error event.",
            )


@router.get("/messages/{msg_id}/stream")
async def stream_message(
    msg_id: UUID,
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> EventSourceResponse:
    """SSE stream for an agent message."""
    message = (
        await db.execute(select(Message).where(Message.id == msg_id).with_for_update())
    ).scalar_one_or_none()
    if not message:
        raise HTTPException(
            404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )

    # Ownership check via parent conversation
    await _get_owned_conversation(db, user.id, message.conversation_id)
    await cleanup_stale_streaming_messages(db)

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

    session = await stream_run_manager.get(message.id)
    if session is not None:
        return EventSourceResponse(stream_run_manager.subscribe(session))

    if message.status == "streaming":
        await _mark_orphaned_stream_error(db, message)
        event = StreamChunk(
            event_type="error",
            error_code="stream_session_lost",
            error="Agent stream was interrupted before completion. Please retry.",
        ).to_sse()
        return EventSourceResponse(_single_sse_event(event))

    if message.status != "pending":
        raise HTTPException(
            409,
            detail={
                "error": {
                    "code": "MESSAGE_NOT_STREAMABLE",
                    "message": "Only pending agent messages can start a stream",
                }
            },
        )

    message.status = "streaming"
    await db.commit()
    session = await stream_run_manager.start(message)
    return EventSourceResponse(stream_run_manager.subscribe(session))
