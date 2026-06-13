"""SSE stream endpoint — Owner: B1.

This is the ★ critical integration point ★ between B1 (routing/persistence) and
B2 (Agent layer). B1 calls `agents.registry.get_adapter()` and pipes the
resulting AsyncIterator[StreamChunk] into SSE events.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.orchestrator.planner import llm_planning_enabled
from app.agents.registry import ORCHESTRATOR_AGENT_ID, AgentNotFoundError, get_adapter
from app.agents.types import StreamChunk
from app.api.v1.conversations import _get_owned_conversation
from app.api.v1.stream_accumulator import StreamContentAccumulator
from app.api.v1.stream_orchestrator_context import (
    apply_orchestrator_stream_context,
    cancel_orchestrator_run,
    interrupt_orchestrator_run,
)
from app.api.v1.stream_preview import maybe_autostart_platform_preview
from app.core.config import settings
from app.core.database import SessionFactory
from app.core.deps import DbSession, get_current_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageOut
from app.services.context.compression import TOTAL_TOKEN_BUDGET
from app.services.context_builder import build_context
from app.services.event_service import event_service
from app.services.memory_hub import MemoryHubService
from app.services.message_lifecycle import cleanup_stale_streaming_messages
from app.services.queued_messages import QueuedDispatch, dispatch_next_queued_message
from app.services.stream_run_manager import StreamRunSession, stream_run_manager
from app.services.turn_controls import expire_pending_controls
from app.services.workspace_service import WorkspaceService
from app.services.workspace_workflow_runtime import WorkspaceWorkflowRuntimeService

router = APIRouter()

_ContentAccumulator = StreamContentAccumulator
workflow_runtime_service = WorkspaceWorkflowRuntimeService()
ERROR_TEXT_MAX_CHARS = 1200
GENERIC_STREAM_ERROR_TEXT = "Agent stream failed. Please retry."
GENERIC_INTERRUPTED_TEXT = "已打断本次回复，可以继续补充要求。"
CONTEXT_MAX_TOKENS_LIMIT = 200_000
DEFAULT_PLANNER_CONTEXT_MAX_TOKENS = 128_000
PLANNER_CONTEXT_MAX_TOKENS_LIMIT = 1_000_000
ORPHANED_STREAM_RECOVERY_TIMEOUT_SECONDS = 10.0
ORPHANED_STREAM_RECOVERY_POLL_SECONDS = 0.5


class StreamDisconnectedError(RuntimeError):
    """Raised when the client disconnects while an adapter is still running."""


class StreamInterruptedError(RuntimeError):
    """Raised when the user explicitly interrupts a running agent turn."""


class StreamTimeoutError(RuntimeError):
    """Raised when an adapter stream exceeds the B1 stream budget."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _configured_context_max_tokens(agent_id: str, config: dict[str, Any]) -> int:
    keys = (
        ("orchestrator_context_max_tokens", "context_max_tokens")
        if agent_id == ORCHESTRATOR_AGENT_ID
        else ("context_max_tokens",)
    )
    for key in keys:
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value < 1:
            continue
        return min(value, CONTEXT_MAX_TOKENS_LIMIT)
    return TOTAL_TOKEN_BUDGET


def _configured_planner_context_max_tokens(config: dict[str, Any]) -> int:
    value = config.get("planner_context_max_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return DEFAULT_PLANNER_CONTEXT_MAX_TOKENS
    return min(value, PLANNER_CONTEXT_MAX_TOKENS_LIMIT)


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


async def _next_chunk_with_timeout_or_interrupt(
    iterator: AsyncIterator[StreamChunk],
    *,
    interrupt_event: asyncio.Event | None,
    timeout_seconds: float | None = None,
    timeout_error_code: str = "stream_timeout",
) -> StreamChunk:
    next_task: asyncio.Task[StreamChunk] = asyncio.create_task(
        _anext_stream_chunk(iterator)
    )
    interrupt_task: asyncio.Task[bool] | None = None
    tasks: set[asyncio.Task[Any]] = {next_task}
    if interrupt_event is not None:
        interrupt_task = asyncio.create_task(interrupt_event.wait())
        tasks.add(interrupt_task)
    try:
        done, _ = await asyncio.wait(
            tasks,
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            for task in tasks:
                await _cancel_task_with_budget(task)
            await _close_async_iterator(iterator)
            raise StreamTimeoutError(
                timeout_error_code,
                "Agent stream timed out before the Agent finished.",
            )
        if interrupt_task is not None and interrupt_task in done:
            await _cancel_task_with_budget(next_task)
            await _close_async_iterator(iterator)
            raise StreamInterruptedError("User interrupted this agent turn.")
        if interrupt_task is not None:
            await _cancel_task_with_budget(interrupt_task)
        return next_task.result()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def _close_async_iterator(iterator: AsyncIterator[StreamChunk]) -> None:
    aclose = getattr(iterator, "aclose", None)
    if callable(aclose):
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(aclose(), timeout=0.5)


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
    refreshed.content = _error_content_blocks(accumulator, text)
    refreshed.status = "error"
    message.status = "error"
    try:
        await db.commit()
    except Exception:
        await db.rollback()


async def _mark_stream_interrupted(
    db: AsyncSession,
    message: Message,
    accumulator: _ContentAccumulator,
) -> None:
    message_id = message.id
    with contextlib.suppress(Exception):
        await db.rollback()
    refreshed = await db.get(Message, message_id)
    if refreshed is None:
        return
    refreshed.content = _interrupted_content_blocks(accumulator)
    refreshed.status = "interrupted"
    message.status = "interrupted"
    try:
        await _record_message_terminal_event(db, refreshed)
        await db.commit()
    except Exception:
        await db.rollback()


async def _persist_stream_error(
    db: AsyncSession,
    message: Message,
    accumulator: _ContentAccumulator,
    chunk: StreamChunk,
) -> None:
    message.content = _error_content_blocks(
        accumulator,
        _chunk_error_text(chunk),
        agent_id=chunk.agent_id,
    )
    message.status = "error"
    await _record_message_terminal_event(db, message)
    await db.commit()


async def _persist_stream_interrupted(
    db: AsyncSession,
    message: Message,
    accumulator: _ContentAccumulator,
) -> None:
    message.content = _interrupted_content_blocks(accumulator)
    message.status = "interrupted"
    await _record_message_terminal_event(db, message)
    await db.commit()


def _error_content_blocks(
    accumulator: _ContentAccumulator,
    text: str,
    *,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    accumulator.finalize_task_cards(success=False)
    content = accumulator.to_list()
    error_text = _safe_error_text(text)
    if _content_has_error_text(content, error_text):
        return content
    error_block: dict[str, Any] = {"type": "text", "text": error_text}
    if agent_id:
        error_block["agent_id"] = agent_id
    return [*content, error_block]


def _interrupted_content_blocks(
    accumulator: _ContentAccumulator,
) -> list[dict[str, Any]]:
    accumulator.finalize_interrupted()
    content = accumulator.to_list()
    if content:
        return content
    return [{"type": "text", "text": GENERIC_INTERRUPTED_TEXT}]


def _chunk_error_text(chunk: StreamChunk) -> str:
    error = _safe_error_text(chunk.error or "")
    if chunk.error_code and chunk.error_code not in error:
        return f"{chunk.error_code}: {error}"
    return error


def _safe_error_text(text: str) -> str:
    cleaned = " ".join(str(text or "").replace("\x00", "").split())
    if not cleaned:
        return GENERIC_STREAM_ERROR_TEXT
    if len(cleaned) > ERROR_TEXT_MAX_CHARS:
        return f"{cleaned[:ERROR_TEXT_MAX_CHARS]}..."
    return cleaned


def _content_has_error_text(content: list[dict[str, Any]], error_text: str) -> bool:
    normalized = _safe_error_text(error_text)
    return any(
        block.get("type") == "text" and normalized in str(block.get("text") or "")
        for block in content
    )


async def _dispatch_queued_next_payload(
    db: AsyncSession,
    message: Message,
) -> dict[str, Any] | None:
    conversation_id = message.conversation_id
    if message.status in {"done", "error", "interrupted"}:
        await _extract_terminal_memories(db, message)
    dispatch = await dispatch_next_queued_message(
        db,
        conversation_id=conversation_id,
    )
    if dispatch is None:
        return None
    return _queued_dispatch_payload(dispatch)


def _queued_dispatch_payload(dispatch: QueuedDispatch) -> dict[str, Any]:
    return {
        "user_message": MessageOut.model_validate(dispatch.user_message).model_dump(mode="json"),
        "agent_message": MessageOut.model_validate(dispatch.agent_message).model_dump(mode="json"),
        "queue_remaining_count": dispatch.queue_remaining_count,
    }


async def _extract_terminal_memories(db: AsyncSession, message: Message) -> None:
    try:
        await MemoryHubService().extract_candidates_for_terminal_message(
            db,
            agent_message=message,
        )
        await db.commit()
    except Exception:
        await db.rollback()


async def _record_message_terminal_event(db: AsyncSession, message: Message) -> None:
    conversation = await db.get(Conversation, message.conversation_id)
    if conversation is None:
        return
    await event_service.record(
        db,
        user_id=conversation.user_id,
        event_type="message.terminal",
        resource_type="message",
        resource_id=message.id,
        conversation_id=message.conversation_id,
        payload={
            "agent_id": message.agent_id,
            "status": message.status,
            "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
        },
    )


async def _recover_orphaned_stream_events(
    message_id: UUID,
) -> AsyncIterator[dict[str, str]]:
    """Wait briefly for a streaming message to reach its persisted terminal state.

    The stream runner is in-process while the message state is persisted in the
    database. During reloads or duplicate subscriptions the DB can say
    ``streaming`` while this process no longer has a live session. That state is
    recoverable and should not be persisted as an error.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ORPHANED_STREAM_RECOVERY_TIMEOUT_SECONDS
    while True:
        async with SessionFactory() as db:
            message = await db.get(Message, message_id)
            if message is None:
                yield StreamChunk(
                    event_type="error",
                    error_code="message_not_found",
                    error="Message not found.",
                ).to_sse()
                return
            if message.status == "done":
                yield StreamChunk(
                    event_type="done",
                    status="done",
                    message_id=str(message.id),
                    conversation_id=str(message.conversation_id),
                    agent_id=message.agent_id,
                    total_blocks=len(message.content or []),
                ).to_sse()
                return
            if message.status == "interrupted":
                yield StreamChunk(
                    event_type="interrupted",
                    status="interrupted",
                    message_id=str(message.id),
                    conversation_id=str(message.conversation_id),
                    agent_id=message.agent_id,
                    total_blocks=len(message.content or []),
                ).to_sse()
                return
            if message.status == "error":
                error_text = GENERIC_STREAM_ERROR_TEXT
                for block in message.content or []:
                    if block.get("type") == "text" and str(block.get("text") or "").strip():
                        error_text = _safe_error_text(str(block.get("text") or ""))
                        break
                yield StreamChunk(
                    event_type="error",
                    error_code="stream_terminal_error",
                    error=error_text,
                    message_id=str(message.id),
                    conversation_id=str(message.conversation_id),
                    agent_id=message.agent_id,
                ).to_sse()
                return
        if loop.time() >= deadline:
            return
        await asyncio.sleep(ORPHANED_STREAM_RECOVERY_POLL_SECONDS)


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


def _is_child_message_chunk(chunk: StreamChunk, parent_message: Message) -> bool:
    return bool(chunk.message_id and chunk.message_id != str(parent_message.id))


async def _feed_child_message_chunk(
    stream_config: dict[str, Any] | None,
    chunk: StreamChunk,
) -> StreamChunk | None:
    if chunk.event_type in {"message_start", "message_done", "message_error"}:
        return None
    writer = (stream_config or {}).get("orchestrator_group_message_writer")
    feed = getattr(writer, "feed", None)
    if not callable(feed):
        return None
    child_error = await feed(chunk)
    return child_error if isinstance(child_error, StreamChunk) else None


async def _fail_open_child_messages(
    stream_config: dict[str, Any] | None,
    error: str,
) -> AsyncIterator[StreamChunk]:
    writer = (stream_config or {}).get("orchestrator_group_message_writer")
    fail_open = getattr(writer, "fail_open_messages", None)
    if not callable(fail_open):
        return
    for chunk in await fail_open(error):
        yield chunk


async def _interrupt_open_child_messages(
    stream_config: dict[str, Any] | None,
) -> AsyncIterator[StreamChunk]:
    writer = (stream_config or {}).get("orchestrator_group_message_writer")
    interrupt_open = getattr(writer, "interrupt_open_messages", None)
    if not callable(interrupt_open):
        return
    for chunk in await interrupt_open():
        yield chunk


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
    *,
    session: StreamRunSession | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Run an agent message and yield SSE-formatted events."""
    accumulator = _ContentAccumulator()
    stream_claimed = False
    stream_config: dict[str, Any] | None = None
    try:
        if not message.agent_id:
            chunk = StreamChunk(
                event_type="error",
                error_code="missing_agent",
                error="Message has no agent_id",
            )
            await _persist_stream_error(db, message, accumulator, chunk)
            queued_next = await _dispatch_queued_next_payload(db, message)
            if queued_next is not None:
                await db.commit()
            yield chunk.model_copy(update={"queued_next": queued_next}).to_sse()
            return

        adapter = await get_adapter(message.agent_id, db)
        adapter_default_config = getattr(adapter, "default_config", {})
        if not isinstance(adapter_default_config, dict):
            adapter_default_config = {}
        context_max_tokens = _configured_context_max_tokens(
            message.agent_id,
            adapter_default_config,
        )
        history = await build_context(
            db,
            message.conversation_id,
            current_agent_id=message.agent_id,
            agent_message_id=message.id,
            max_tokens=context_max_tokens,
        )
        planner_context_messages = None
        if message.agent_id == ORCHESTRATOR_AGENT_ID and llm_planning_enabled(
            adapter_default_config
        ):
            planner_context_messages = await build_context(
                db,
                message.conversation_id,
                current_agent_id=message.agent_id,
                agent_message_id=message.id,
                max_tokens=_configured_planner_context_max_tokens(
                    adapter_default_config
                ),
            )
        workspace = await WorkspaceService().get_or_create(db, message.conversation_id)
        history, stream_config = await apply_orchestrator_stream_context(
            db,
            message,
            adapter,
            history,
            planner_context_messages=planner_context_messages,
        )

        stream_claimed = True

        final_done: StreamChunk | None = None
        next_block_index = 0
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        last_activity_at = started_at
        stream_config = {
            **(stream_config or {}),
            "turn_options": message.turn_options or {},
            "runtime_context": {
                "conversation_id": str(message.conversation_id),
                "agent_message_id": str(message.id),
                "agent_id": message.agent_id,
            },
        }
        if session is not None:
            stream_config["runtime_interrupt_event"] = session.interrupt_event
            stream_config["runtime_control"] = {
                "interrupt_event": session.interrupt_event,
                "active_agent_message_id": str(message.id),
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
                chunk = await _next_chunk_with_timeout_or_interrupt(
                    adapter_iterator,
                    interrupt_event=session.interrupt_event if session else None,
                    timeout_seconds=wait_timeout,
                    timeout_error_code=timeout_code,
                )
            except StopAsyncIteration:
                break
            last_activity_at = loop.time()
            if chunk.block_index is not None:
                next_block_index = max(next_block_index, chunk.block_index + 1)
            if chunk.event_type == "done":
                if session is not None and session.interrupt_event.is_set():
                    raise StreamInterruptedError("User interrupted this agent turn.")
                final_done = chunk
                if chunk.total_blocks is not None:
                    next_block_index = max(next_block_index, chunk.total_blocks)
                break
            if _is_child_message_chunk(chunk, message):
                child_error = await _feed_child_message_chunk(stream_config, chunk)
                yield chunk.to_sse()
                if child_error is not None:
                    yield child_error.to_sse()
                continue
            accumulator_error = accumulator.feed(chunk)
            if accumulator_error is not None:
                await _persist_stream_error(db, message, accumulator, accumulator_error)
                queued_next = await _dispatch_queued_next_payload(db, message)
                if queued_next is not None:
                    await db.commit()
                yield accumulator_error.model_copy(
                    update={"queued_next": queued_next}
                ).to_sse()
                return
            if chunk.event_type == "error":
                await _persist_stream_error(db, message, accumulator, chunk)
                queued_next = await _dispatch_queued_next_payload(db, message)
                if queued_next is not None:
                    await db.commit()
                yield chunk.model_copy(update={"queued_next": queued_next}).to_sse()
                return
            yield chunk.to_sse()

        # Persist
        if final_done is not None:
            if session is not None and session.interrupt_event.is_set():
                raise StreamInterruptedError("User interrupted this agent turn.")
            try:
                preview_chunks, next_block_index = await asyncio.wait_for(
                    maybe_autostart_platform_preview(
                        db=db,
                        message=message,
                        history=history,
                        workspace_path=Path(workspace.root_path),
                        block_index=next_block_index,
                        existing_blocks=accumulator.to_list(),
                    ),
                    timeout=max(1.0, float(settings.preview_start_timeout_seconds) + 2.0),
                )
            except TimeoutError:
                preview_chunks = []
            for preview_chunk in preview_chunks:
                accumulator_error = accumulator.feed(preview_chunk)
                if accumulator_error is not None:
                    await _persist_stream_error(db, message, accumulator, accumulator_error)
                    queued_next = await _dispatch_queued_next_payload(db, message)
                    if queued_next is not None:
                        await db.commit()
                    yield accumulator_error.model_copy(
                        update={"queued_next": queued_next}
                    ).to_sse()
                    return
                yield preview_chunk.to_sse()
            if session is not None and session.interrupt_event.is_set():
                raise StreamInterruptedError("User interrupted this agent turn.")
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
        await _record_message_terminal_event(db, message)
        await db.commit()
        queued_next = await _dispatch_queued_next_payload(db, message)
        if queued_next is not None:
            await db.commit()
        if final_done is not None and not has_orphaned_tool_call:
            yield final_done.model_copy(
                update={"total_blocks": next_block_index, "queued_next": queued_next}
            ).to_sse()
        elif has_orphaned_tool_call:
            yield StreamChunk(
                event_type="error",
                error_code="orphan_tool_call",
                error="Agent stream ended with an incomplete tool call.",
                queued_next=queued_next,
            ).to_sse()
    except StreamInterruptedError:
        await interrupt_orchestrator_run(stream_config)
        async for child_chunk in _interrupt_open_child_messages(stream_config):
            yield child_chunk.to_sse()
        await _persist_stream_interrupted(db, message, accumulator)
        queued_next = await _dispatch_queued_next_payload(db, message)
        if queued_next is not None:
            await db.commit()
        yield StreamChunk(
            event_type="interrupted",
            status="interrupted",
            message_id=str(message.id),
            conversation_id=str(message.conversation_id),
            agent_id=message.agent_id,
            total_blocks=len(message.content or []),
            queued_next=queued_next,
        ).to_sse()
    except StreamTimeoutError as e:
        await cancel_orchestrator_run(stream_config)
        async for child_error in _fail_open_child_messages(stream_config, str(e)):
            yield child_error.to_sse()
        await _mark_stream_error(db, message, accumulator, str(e))
        queued_next = await _dispatch_queued_next_payload(db, message)
        if queued_next is not None:
            await db.commit()
        yield StreamChunk(
            event_type="error",
            error_code=e.error_code,
            error=str(e),
            queued_next=queued_next,
        ).to_sse()
    except asyncio.CancelledError:
        await cancel_orchestrator_run(stream_config)
        async for child_error in _fail_open_child_messages(
            stream_config,
            "Stream was cancelled before the Agent finished.",
        ):
            yield child_error.to_sse()
        await _mark_stream_error(
            db,
            message,
            accumulator,
            "Stream was cancelled before the Agent finished.",
        )
        raise
    except AgentNotFoundError as e:
        chunk = StreamChunk(
            event_type="error", error_code="agent_not_found", error=str(e)
        )
        async for child_error in _fail_open_child_messages(stream_config, str(e)):
            yield child_error.to_sse()
        await _persist_stream_error(db, message, accumulator, chunk)
        queued_next = await _dispatch_queued_next_payload(db, message)
        if queued_next is not None:
            await db.commit()
        yield chunk.model_copy(update={"queued_next": queued_next}).to_sse()
    except Exception as e:  # noqa: BLE001
        async for child_error in _fail_open_child_messages(stream_config, str(e)):
            yield child_error.to_sse()
        await _mark_stream_error(db, message, accumulator, str(e))
        queued_next = await _dispatch_queued_next_payload(db, message)
        if queued_next is not None:
            await db.commit()
        yield StreamChunk(
            event_type="error",
            error_code="internal_error",
            error=str(e),
            queued_next=queued_next,
        ).to_sse()
    finally:
        if stream_claimed and message.status in {"pending", "streaming"}:
            await cancel_orchestrator_run(stream_config)
            async for child_error in _fail_open_child_messages(
                stream_config,
                "Agent stream ended before a final done or error event.",
            ):
                yield child_error.to_sse()
            await _mark_stream_error(
                db,
                message,
                accumulator,
                "Agent stream ended before a final done or error event.",
            )
            queued_next = await _dispatch_queued_next_payload(db, message)
            if queued_next is not None:
                await db.commit()
        if message.status in {"done", "error", "interrupted"}:
            await expire_pending_controls(message.id)


async def _run_stream_session(session: StreamRunSession) -> None:
    try:
        async with SessionFactory() as db:
            message = await db.get(Message, session.message_id)
            if message is None:
                return
            async for event in _runtime_event_generator(db, message, session=session):
                await stream_run_manager.publish(session, event)
    finally:
        await stream_run_manager.finish(session)


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
        # The endpoint initially locks the message row so only one request can
        # claim a pending stream. When a runtime session already exists, this
        # request is only an additional subscriber; release the row before
        # returning the long-lived SSE response so the background runner can
        # persist the terminal message state.
        await db.rollback()
        return EventSourceResponse(stream_run_manager.subscribe(session))

    if message.status == "streaming":
        recovery_message_id = message.id
        await db.rollback()
        return EventSourceResponse(_recover_orphaned_stream_events(recovery_message_id))

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
    session = await stream_run_manager.prepare(message)
    try:
        await db.commit()
    except Exception:
        await stream_run_manager.finish(session)
        raise
    await stream_run_manager.start_prepared(session, _run_stream_session)
    return EventSourceResponse(stream_run_manager.subscribe(session))
