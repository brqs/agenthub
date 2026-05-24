"""Conversation routes — Owner: B1.

TODO(B1): full implementation. This is a skeleton.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select

from app.core.deps import DbSession, get_current_user
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.conversation import (
    ConversationList,
    ConversationOut,
    CreateConversationRequest,
    UpdateConversationRequest,
)

router = APIRouter()


@router.get("", response_model=ConversationList)
async def list_conversations(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    archived: bool = Query(default=False),
    pinned_only: bool = Query(default=False),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConversationList:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if not archived:
        stmt = stmt.where(Conversation.is_archived.is_(False))
    if pinned_only:
        stmt = stmt.where(Conversation.is_pinned.is_(True))
    if search:
        stmt = stmt.where(Conversation.title.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = (
        stmt.order_by(desc(Conversation.is_pinned), desc(Conversation.last_message_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()

    return ConversationList(
        items=[ConversationOut.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: CreateConversationRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationOut:
    # TODO(B1): validate agent_ids exist
    conv = Conversation(
        user_id=user.id,
        title=payload.title,
        mode=payload.mode,
        agent_ids=payload.agent_ids,
    )
    db.add(conv)
    await db.flush()
    return ConversationOut.model_validate(conv)


async def _get_owned_conversation(db, user_id: UUID, conv_id: UUID) -> Conversation:
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Not found"}},
        )
    if conv.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}},
        )
    return conv


@router.get("/{conv_id}", response_model=ConversationOut)
async def get_conversation(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationOut:
    conv = await _get_owned_conversation(db, user.id, conv_id)
    return ConversationOut.model_validate(conv)


@router.patch("/{conv_id}", response_model=ConversationOut)
async def update_conversation(
    conv_id: UUID,
    payload: UpdateConversationRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationOut:
    conv = await _get_owned_conversation(db, user.id, conv_id)
    if payload.title is not None:
        conv.title = payload.title
    if payload.is_pinned is not None:
        conv.is_pinned = payload.is_pinned
    if payload.is_archived is not None:
        conv.is_archived = payload.is_archived
    await db.flush()
    return ConversationOut.model_validate(conv)


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    conv = await _get_owned_conversation(db, user.id, conv_id)
    await db.delete(conv)
