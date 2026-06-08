"""Message routes — Owner: B1.

TODO(B1):
  - Implement send (POST) — create user_message + pending agent_message.
  - Implement cursor pagination for list.
  - Implement regenerate.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.v1.conversations import _get_owned_conversation, _validate_visible_agent_ids
from app.core.deps import DbSession, get_current_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_queue import MessageQueueEntry
from app.models.upload import Upload
from app.models.user import User
from app.schemas.message import (
    GuidanceRequest,
    InterruptMessageResponse,
    MessageList,
    MessageOut,
    QueueMergeRequest,
    QueueMessageRequest,
    QueueMessageResponse,
    QueueReorderRequest,
    QueueReorderResponse,
    SendMessageRequest,
    SendMessageResponse,
    SideChatRequest,
    TurnControlResponse,
    UpdateMessageRequest,
    UpdateQueuedMessageRequest,
)
from app.services.message_lifecycle import cleanup_stale_streaming_messages
from app.services.queued_messages import (
    delete_queued_user_message,
    dispatch_next_queued_message,
    enqueue_user_message,
    get_active_agent_message,
    get_queue_entry_for_user_message,
    merge_queued_messages,
    promote_queued_message_to_front,
    reorder_queued_messages,
    update_queued_user_message,
)
from app.services.stream_run_manager import stream_run_manager
from app.services.turn_controls import (
    create_guidance_control,
    create_side_chat_control,
)
from app.services.upload_service import upload_service

router = APIRouter()
INTERRUPTED_FALLBACK_BLOCK = {
    "type": "text",
    "text": "已打断本次回复，可以继续补充要求。",
}


async def _get_active_agent_message(db: DbSession, conv_id: UUID) -> Message | None:
    return await get_active_agent_message(db, conv_id)


async def _resolve_target_agent_id(
    db: DbSession,
    user_id: UUID,
    conv: Conversation,
    target_agent_id: str | None,
) -> str:
    resolved_target_agent_id = target_agent_id
    if not resolved_target_agent_id:
        if conv.mode == "single" and len(conv.agent_ids) == 1:
            resolved_target_agent_id = conv.agent_ids[0]
        else:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "MISSING_TARGET_AGENT",
                        "message": "target_agent_id required for group mode",
                    }
                },
            )
    if resolved_target_agent_id not in conv.agent_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": "target_agent_id is not part of this conversation",
                }
            },
        )
    await _validate_visible_agent_ids(db, user_id, [resolved_target_agent_id])
    return resolved_target_agent_id


async def _get_queued_user_message(db: DbSession, user_id: UUID, msg_id: UUID) -> Message:
    msg = await db.get(Message, msg_id)
    if not msg:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user_id, msg.conversation_id)
    if msg.role != "user" or msg.status != "queued":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "MESSAGE_NOT_QUEUED",
                    "message": "Only queued user messages can be modified",
                }
            },
        )
    return msg


async def _get_queued_entry_or_409(db: DbSession, msg_id: UUID) -> MessageQueueEntry:
    entry = await get_queue_entry_for_user_message(db, user_message_id=msg_id)
    if entry is None or entry.state != "queued":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "QUEUE_ENTRY_NOT_QUEUED",
                    "message": "Queued message has already been dispatched",
                }
            },
        )
    return entry


async def _content_with_attachments(
    db: DbSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    content: list[Any],
    attachment_ids: list[UUID],
) -> tuple[list[dict[str, Any]], list[Upload]]:
    uploads = await upload_service.validate_ready_uploads(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        upload_ids=attachment_ids,
    )
    blocks = [block.model_dump() for block in content]
    blocks.extend(upload_service.attachment_blocks(uploads))
    return blocks, uploads


async def _get_active_agent_message_for_control(
    db: DbSession,
    user_id: UUID,
    msg_id: UUID,
) -> Message:
    msg = await db.get(Message, msg_id)
    if not msg:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user_id, msg.conversation_id)
    if msg.role != "agent" or msg.status not in {"pending", "streaming"}:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "NO_ACTIVE_AGENT_RESPONSE",
                    "message": "Turn controls require an active agent response",
                }
            },
        )
    return msg


def _content_text(content: Sequence[object]) -> str:
    parts: list[str] = []
    for block in content:
        value = block.model_dump() if hasattr(block, "model_dump") else block
        if isinstance(value, dict) and value.get("type") == "text":
            parts.append(str(value.get("text") or ""))
    return "\n".join(part for part in parts if part.strip()).strip()


async def _queue_position_map(
    db: DbSession,
    message_ids: list[UUID],
) -> dict[UUID, int]:
    if not message_ids:
        return {}
    stmt = select(MessageQueueEntry.user_message_id, MessageQueueEntry.position).where(
        MessageQueueEntry.user_message_id.in_(message_ids)
    )
    rows = (await db.execute(stmt)).all()
    return {row[0]: int(row[1]) for row in rows}


def _message_out(message: Message, *, queue_position: int | None = None) -> MessageOut:
    out = MessageOut.model_validate(message)
    out.queue_position = queue_position
    return out


async def _touch_conversation(db: DbSession, user_id: UUID, conv_id: UUID) -> None:
    conv = await _get_owned_conversation(db, user_id, conv_id)
    conv.last_message_at = datetime.now(UTC)


# ─── List messages in conversation ───
@router.get(
    "/conversations/{conv_id}/messages",
    response_model=MessageList,
)
async def list_messages(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    direction: str = Query(default="before", pattern="^(before|after)$"),
) -> MessageList:
    await _get_owned_conversation(db, user.id, conv_id)

    cursor_message: Message | None = None
    if cursor:
        try:
            cursor_id = UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_CURSOR",
                        "message": "Message cursor must be a message id",
                    }
                },
            ) from exc
        cursor_message = await db.get(Message, cursor_id)
        if cursor_message is None or cursor_message.conversation_id != conv_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_CURSOR",
                        "message": "Message cursor does not belong to this conversation",
                    }
                },
            )

    stmt = select(Message).where(Message.conversation_id == conv_id)
    if cursor_message is not None:
        if direction == "before":
            stmt = stmt.where(Message.created_at < cursor_message.created_at)
        else:
            stmt = stmt.where(Message.created_at > cursor_message.created_at)

    if direction == "after" and cursor_message is not None:
        page = (
            (await db.execute(stmt.order_by(Message.created_at.asc()).limit(limit + 1)))
            .scalars()
            .all()
        )
        has_more = len(page) > limit
        items = page[:limit]
        next_cursor = str(items[-1].id) if has_more and items else None
    else:
        page = (
            (await db.execute(stmt.order_by(Message.created_at.desc()).limit(limit + 1)))
            .scalars()
            .all()
        )
        has_more = len(page) > limit
        items = list(reversed(page[:limit]))
        next_cursor = str(items[0].id) if has_more and items else None

    queue_positions = await _queue_position_map(
        db,
        [message.id for message in items if message.status == "queued"],
    )
    return MessageList(
        items=[
            _message_out(message, queue_position=queue_positions.get(message.id))
            for message in items
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ─── Send message (creates user msg + pending agent msg) ───
@router.post(
    "/conversations/{conv_id}/messages",
    response_model=SendMessageResponse,
    status_code=201,
)
async def send_message(
    conv_id: UUID,
    payload: SendMessageRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> SendMessageResponse:
    conv = await _get_owned_conversation(db, user.id, conv_id)

    target_agent_id = await _resolve_target_agent_id(
        db,
        user.id,
        conv,
        payload.target_agent_id,
    )

    await cleanup_stale_streaming_messages(db)
    active_message = await _get_active_agent_message(db, conv_id)
    if active_message is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "CONVERSATION_BUSY",
                    "message": "Conversation already has an agent response in progress",
                    "details": {
                        "message_id": str(active_message.id),
                        "agent_id": active_message.agent_id,
                        "status": active_message.status,
                    },
                }
            },
        )

    content, uploads = await _content_with_attachments(
        db,
        user_id=user.id,
        conversation_id=conv_id,
        content=payload.content,
        attachment_ids=payload.attachment_ids,
    )

    # Create user message
    user_msg = Message(
        conversation_id=conv_id,
        role="user",
        content=content,
        status="done",
    )
    db.add(user_msg)
    await db.flush()
    await upload_service.link_message_attachments(db, message_id=user_msg.id, uploads=uploads)

    # Create pending agent message
    agent_msg = Message(
        conversation_id=conv_id,
        role="agent",
        agent_id=target_agent_id,
        content=[],
        reply_to_id=user_msg.id,
        status="pending",
    )
    db.add(agent_msg)

    # Bump conversation activity
    conv.last_message_at = datetime.now(UTC)

    await db.flush()
    return SendMessageResponse(
        user_message=MessageOut.model_validate(user_msg),
        agent_message=MessageOut.model_validate(agent_msg),
    )


# ─── Queued next-turn messages ───
@router.post(
    "/conversations/{conv_id}/queued-messages",
    response_model=QueueMessageResponse,
    status_code=201,
)
async def queue_message(
    conv_id: UUID,
    payload: QueueMessageRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> QueueMessageResponse:
    conv = await _get_owned_conversation(db, user.id, conv_id)
    target_agent_id = await _resolve_target_agent_id(
        db,
        user.id,
        conv,
        payload.target_agent_id,
    )
    await cleanup_stale_streaming_messages(db)
    active_message = await _get_active_agent_message(db, conv_id)
    if active_message is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "NO_ACTIVE_AGENT_RESPONSE",
                    "message": "Queued messages require an active agent response",
                }
            },
        )
    content, uploads = await _content_with_attachments(
        db,
        user_id=user.id,
        conversation_id=conv_id,
        content=payload.content,
        attachment_ids=payload.attachment_ids,
    )
    queued_message, _entry, position = await enqueue_user_message(
        db,
        conversation=conv,
        target_agent_id=target_agent_id,
        content=content,
    )
    await upload_service.link_message_attachments(
        db,
        message_id=queued_message.id,
        uploads=uploads,
    )
    await db.commit()
    await db.refresh(queued_message)
    return QueueMessageResponse(
        queued_message=_message_out(queued_message, queue_position=position),
        queue_position=position,
    )


@router.patch("/queued-messages/{msg_id}", response_model=QueueMessageResponse)
async def update_queued_message(
    msg_id: UUID,
    payload: UpdateQueuedMessageRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> QueueMessageResponse:
    msg = await _get_queued_user_message(db, user.id, msg_id)
    conv = await _get_owned_conversation(db, user.id, msg.conversation_id)
    entry = await _get_queued_entry_or_409(db, msg.id)
    if payload.content is None and payload.target_agent_id is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "EMPTY_QUEUED_MESSAGE_UPDATE",
                    "message": "content or target_agent_id is required",
                }
            },
        )
    target_agent_id = (
        await _resolve_target_agent_id(db, user.id, conv, payload.target_agent_id)
        if payload.target_agent_id is not None
        else None
    )
    position = await update_queued_user_message(
        db,
        user_message=msg,
        queue_entry=entry,
        content=(
            [block.model_dump() for block in payload.content]
            if payload.content is not None
            else None
        ),
        target_agent_id=target_agent_id,
    )
    await db.commit()
    await db.refresh(msg)
    return QueueMessageResponse(
        queued_message=_message_out(msg, queue_position=position),
        queue_position=position,
    )


@router.delete("/queued-messages/{msg_id}", status_code=204)
async def delete_queued_message(
    msg_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    msg = await _get_queued_user_message(db, user.id, msg_id)
    entry = await _get_queued_entry_or_409(db, msg.id)
    await delete_queued_user_message(db, user_message=msg, queue_entry=entry)
    await db.commit()


@router.post(
    "/conversations/{conv_id}/queued-messages/reorder",
    response_model=QueueReorderResponse,
)
async def reorder_queued_message_api(
    conv_id: UUID,
    payload: QueueReorderRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> QueueReorderResponse:
    await _get_owned_conversation(db, user.id, conv_id)
    try:
        messages = await reorder_queued_messages(
            db,
            conversation_id=conv_id,
            ordered_user_message_ids=payload.message_ids,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "QUEUE_REORDER_INVALID", "message": str(exc)}},
        ) from exc
    await db.commit()
    for message in messages:
        await db.refresh(message)
    positions = await _queue_position_map(db, [message.id for message in messages])
    return QueueReorderResponse(
        messages=[
            _message_out(message, queue_position=positions.get(message.id))
            for message in messages
        ],
    )


@router.post(
    "/conversations/{conv_id}/queued-messages/merge",
    response_model=QueueMessageResponse,
)
async def merge_queued_message_api(
    conv_id: UUID,
    payload: QueueMergeRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> QueueMessageResponse:
    await _get_owned_conversation(db, user.id, conv_id)
    try:
        merged, position = await merge_queued_messages(
            db,
            conversation_id=conv_id,
            user_message_ids=payload.message_ids,
            separator=payload.separator,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "QUEUE_MERGE_INVALID", "message": str(exc)}},
        ) from exc
    await db.commit()
    await db.refresh(merged)
    return QueueMessageResponse(
        queued_message=_message_out(merged, queue_position=position),
        queue_position=position,
    )


@router.post(
    "/messages/{msg_id}/guidance",
    response_model=TurnControlResponse,
    status_code=201,
)
async def create_guidance(
    msg_id: UUID,
    payload: GuidanceRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> TurnControlResponse:
    active_message = await _get_active_agent_message_for_control(db, user.id, msg_id)
    content = [block.model_dump() for block in payload.content]
    body = _content_text(payload.content)
    try:
        control, user_message = await create_guidance_control(
            db,
            active_message=active_message,
            body=body,
            source_content=content,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": str(exc),
                    "message": "Guidance is not supported for this active agent",
                }
            },
        ) from exc
    await _touch_conversation(db, user.id, active_message.conversation_id)
    await db.commit()
    await db.refresh(control)
    await db.refresh(user_message)
    return TurnControlResponse(
        control=control,
        user_message=MessageOut.model_validate(user_message),
    )


@router.post(
    "/messages/{msg_id}/side-chat",
    response_model=TurnControlResponse,
    status_code=201,
)
async def create_side_chat(
    msg_id: UUID,
    payload: SideChatRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> TurnControlResponse:
    active_message = await _get_active_agent_message_for_control(db, user.id, msg_id)
    content = [block.model_dump() for block in payload.content]
    body = _content_text(payload.content)
    control, user_message, agent_message = await create_side_chat_control(
        db,
        active_message=active_message,
        body=body,
        source_content=content,
    )
    await _touch_conversation(db, user.id, active_message.conversation_id)
    await db.commit()
    await db.refresh(control)
    await db.refresh(user_message)
    await db.refresh(agent_message)
    return TurnControlResponse(
        control=control,
        user_message=MessageOut.model_validate(user_message),
        agent_message=MessageOut.model_validate(agent_message),
    )


@router.post(
    "/queued-messages/{msg_id}/convert-to-guidance",
    response_model=TurnControlResponse,
)
async def convert_queued_message_to_guidance(
    msg_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> TurnControlResponse:
    msg = await _get_queued_user_message(db, user.id, msg_id)
    entry = await _get_queued_entry_or_409(db, msg.id)
    active_message = await _get_active_agent_message(db, msg.conversation_id)
    if active_message is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "NO_ACTIVE_AGENT_RESPONSE",
                    "message": "Queued guidance requires an active agent response",
                }
            },
        )
    try:
        await db.delete(entry)
        msg.status = "done"
        control, user_message = await create_guidance_control(
            db,
            active_message=active_message,
            body=_content_text(msg.content),
            source_content=[
                block
                for block in msg.content
                if not (isinstance(block, dict) and block.get("type") == "turn_control")
            ],
            created_by_message=msg,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": str(exc),
                    "message": "Guidance is not supported for this active agent",
                }
            },
        ) from exc
    await _touch_conversation(db, user.id, active_message.conversation_id)
    await db.commit()
    await db.refresh(control)
    await db.refresh(user_message)
    return TurnControlResponse(
        control=control,
        user_message=MessageOut.model_validate(user_message),
    )


@router.post(
    "/queued-messages/{msg_id}/stop-and-run",
    response_model=InterruptMessageResponse,
)
async def stop_current_and_run_queued_message(
    msg_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> InterruptMessageResponse:
    msg = await _get_queued_user_message(db, user.id, msg_id)
    await _get_queued_entry_or_409(db, msg.id)
    try:
        await promote_queued_message_to_front(
            db,
            conversation_id=msg.conversation_id,
            user_message_id=msg.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "QUEUE_PROMOTE_INVALID", "message": str(exc)}},
        ) from exc
    await db.flush()
    active_message = await _get_active_agent_message(db, msg.conversation_id)
    if active_message is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "NO_ACTIVE_AGENT_RESPONSE",
                    "message": "Stop-and-run requires an active agent response",
                }
            },
        )
    await db.commit()
    return await interrupt_message(active_message.id, db, user, response)


# ─── Pin / Unpin message ───
@router.patch("/messages/{msg_id}", response_model=MessageOut)
async def update_message(
    msg_id: UUID,
    payload: UpdateMessageRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> MessageOut:
    msg = await db.get(Message, msg_id)
    if not msg:
        raise HTTPException(
            404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user.id, msg.conversation_id)

    if payload.is_pinned is not None:
        msg.is_pinned = payload.is_pinned
    await db.flush()
    return MessageOut.model_validate(msg)


@router.post("/messages/{msg_id}/interrupt", response_model=InterruptMessageResponse)
async def interrupt_message(
    msg_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> InterruptMessageResponse:
    msg = await db.get(Message, msg_id)
    if not msg:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user.id, msg.conversation_id)
    if msg.role != "agent":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "NOT_AGENT_MESSAGE",
                    "message": "Only agent messages can be interrupted",
                }
            },
        )

    if msg.status in {"done", "error", "interrupted"}:
        return InterruptMessageResponse(
            state="already_terminal",
            message=MessageOut.model_validate(msg),
        )

    session = await stream_run_manager.request_interrupt(
        msg.id,
        reason="user_interrupt",
    )
    if session is not None:
        terminal = await session.wait_terminal(timeout=0.25)
        await db.refresh(msg)
        if terminal and msg.status == "interrupted":
            return InterruptMessageResponse(
                state="interrupted",
                message=MessageOut.model_validate(msg),
            )
        if terminal and msg.status in {"done", "error"}:
            return InterruptMessageResponse(
                state="already_terminal",
                message=MessageOut.model_validate(msg),
            )
        response.status_code = status.HTTP_202_ACCEPTED
        return InterruptMessageResponse(
            state="interrupting",
            message=MessageOut.model_validate(msg),
        )

    if msg.status == "pending":
        msg.status = "interrupted"
        if not msg.content:
            msg.content = [dict(INTERRUPTED_FALLBACK_BLOCK)]
        await db.commit()
        queued_next = await dispatch_next_queued_message(db, conversation_id=msg.conversation_id)
        if queued_next is not None:
            await db.commit()
        await db.refresh(msg)
        return InterruptMessageResponse(
            state="interrupted",
            message=MessageOut.model_validate(msg),
        )

    if msg.status == "streaming":
        msg.status = "error"
        if not msg.content:
            msg.content = [
                {
                    "type": "text",
                    "text": "Agent stream was interrupted before completion. Please retry.",
                }
            ]
        await db.commit()
        queued_next = await dispatch_next_queued_message(db, conversation_id=msg.conversation_id)
        if queued_next is not None:
            await db.commit()
        await db.refresh(msg)
        return InterruptMessageResponse(
            state="already_terminal",
            message=MessageOut.model_validate(msg),
        )

    return InterruptMessageResponse(
        state="already_terminal",
        message=MessageOut.model_validate(msg),
    )


# ─── Delete message ───
@router.delete("/messages/{msg_id}", status_code=204)
async def delete_message(
    msg_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    msg = await db.get(Message, msg_id)
    if not msg:
        raise HTTPException(
            404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user.id, msg.conversation_id)
    await db.delete(msg)


# ─── Regenerate (TODO B1) ───
@router.post("/messages/{msg_id}/regenerate", response_model=MessageOut, status_code=201)
async def regenerate_message(
    msg_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> MessageOut:
    msg = await db.get(Message, msg_id)
    if not msg:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )
    conv = await _get_owned_conversation(db, user.id, msg.conversation_id)
    if msg.role != "agent":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "NOT_AGENT_MESSAGE",
                    "message": "Only agent messages can be regenerated",
                }
            },
        )
    if msg.agent_id is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "MISSING_TARGET_AGENT",
                    "message": "Missing agent_id",
                }
            },
        )
    if msg.agent_id not in conv.agent_ids:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"}},
        )
    await _validate_visible_agent_ids(db, user.id, [msg.agent_id])
    await cleanup_stale_streaming_messages(db)
    active_message = await _get_active_agent_message(db, msg.conversation_id)
    if active_message is not None and active_message.id != msg.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "CONVERSATION_BUSY",
                    "message": "Conversation already has an agent response in progress",
                    "details": {
                        "message_id": str(active_message.id),
                        "agent_id": active_message.agent_id,
                        "status": active_message.status,
                    },
                }
            },
        )

    new_msg = Message(
        conversation_id=msg.conversation_id,
        role="agent",
        agent_id=msg.agent_id,
        content=[],
        reply_to_id=msg.reply_to_id,
        status="pending",
    )
    await db.delete(msg)
    db.add(new_msg)
    conv.last_message_at = datetime.now(UTC)
    await db.flush()
    return MessageOut.model_validate(new_msg)
