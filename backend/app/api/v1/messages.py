"""Message routes — Owner: B1.

TODO(B1):
  - Implement send (POST) — create user_message + pending agent_message.
  - Implement cursor pagination for list.
  - Implement regenerate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.v1.conversations import _get_owned_conversation, _validate_visible_agent_ids
from app.core.deps import DbSession, get_current_user
from app.models.message import Message
from app.models.user import User
from app.schemas.message import (
    MessageList,
    MessageOut,
    SendMessageRequest,
    SendMessageResponse,
    UpdateMessageRequest,
)

router = APIRouter()


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
    limit: int = Query(default=50, ge=1, le=100),
    direction: str = Query(default="before", pattern="^(before|after)$"),
) -> MessageList:
    await _get_owned_conversation(db, user.id, conv_id)

    # TODO(B1): proper cursor pagination
    stmt = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    items = (await db.execute(stmt)).scalars().all()
    return MessageList(
        items=[MessageOut.model_validate(m) for m in items],
        next_cursor=None,
        has_more=False,
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

    # Resolve target agent
    target_agent_id = payload.target_agent_id
    if not target_agent_id:
        if conv.mode == "single" and len(conv.agent_ids) == 1:
            target_agent_id = conv.agent_ids[0]
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
    if target_agent_id not in conv.agent_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": "target_agent_id is not part of this conversation",
                }
            },
        )
    await _validate_visible_agent_ids(db, user.id, [target_agent_id])

    # Create user message
    user_msg = Message(
        conversation_id=conv_id,
        role="user",
        content=[b.model_dump() for b in payload.content],
        status="done",
    )
    db.add(user_msg)
    await db.flush()

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
