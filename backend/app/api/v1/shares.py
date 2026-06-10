"""Conversation read-only share routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.conversations import _get_owned_conversation
from app.core.deps import DbSession, get_current_user
from app.models.user import User
from app.schemas.share import (
    ConversationShareOut,
    CreateConversationShareRequest,
    PublicConversationShareOut,
)
from app.services.share_service import conversation_share_service

router = APIRouter()


@router.post(
    "/conversations/{conversation_id}/shares",
    response_model=ConversationShareOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation_share(
    conversation_id: UUID,
    payload: CreateConversationShareRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationShareOut:
    conversation = await _get_owned_conversation(db, user.id, conversation_id)
    share, token = await conversation_share_service.create_share(
        db,
        conversation=conversation,
        payload=payload,
    )
    await db.commit()
    await db.refresh(share)
    return conversation_share_service.to_out(share, token=token)


@router.get("/conversations/{conversation_id}/shares", response_model=list[ConversationShareOut])
async def list_conversation_shares(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[ConversationShareOut]:
    await _get_owned_conversation(db, user.id, conversation_id)
    shares = await conversation_share_service.list_shares(
        db,
        conversation_id=conversation_id,
        owner_user_id=user.id,
    )
    return [conversation_share_service.to_out(share) for share in shares]


@router.delete(
    "/conversations/{conversation_id}/shares/{share_id}",
    response_model=ConversationShareOut,
)
async def revoke_conversation_share(
    conversation_id: UUID,
    share_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationShareOut:
    await _get_owned_conversation(db, user.id, conversation_id)
    share = await conversation_share_service.revoke_share(
        db,
        conversation_id=conversation_id,
        owner_user_id=user.id,
        share_id=share_id,
    )
    await db.commit()
    await db.refresh(share)
    return conversation_share_service.to_out(share)


@router.get("/conversation-shares/{token}", response_model=PublicConversationShareOut)
async def get_public_conversation_share(
    token: str,
    db: DbSession,
) -> PublicConversationShareOut:
    snapshot = await conversation_share_service.get_public_snapshot(db, token=token)
    await db.commit()
    return snapshot
