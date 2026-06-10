"""Read-only conversation share service."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_refresh_token
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.session import ConversationShare
from app.schemas.share import (
    ConversationShareOut,
    CreateConversationShareRequest,
    PublicConversationShareOut,
    PublicSharedMessageOut,
)
from app.services.audit_service import record_audit_event
from app.services.event_service import event_service

SHARE_TOKEN_BYTES = 32
SAFE_BLOCK_TYPES = {
    "text",
    "code",
    "diff",
    "web_preview",
    "deployment_status",
    "workflow",
    "task_card",
    "process",
    "clarification",
    "turn_control",
}
ARTIFACT_BLOCK_TYPES = {"file", "attachment"}


class ConversationShareService:
    async def create_share(
        self,
        db: AsyncSession,
        *,
        conversation: Conversation,
        payload: CreateConversationShareRequest,
    ) -> tuple[ConversationShare, str]:
        token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
        share = ConversationShare(
            conversation_id=conversation.id,
            owner_user_id=conversation.user_id,
            token_hash=hash_refresh_token(token),
            include_artifacts=payload.include_artifacts,
            expires_at=payload.expires_at,
        )
        db.add(share)
        await db.flush()
        await record_audit_event(
            db,
            user_id=conversation.user_id,
            action="conversation_share.created",
            resource_type="conversation_share",
            resource_id=share.id,
            metadata={
                "conversation_id": str(conversation.id),
                "include_artifacts": share.include_artifacts,
            },
        )
        await event_service.record(
            db,
            user_id=conversation.user_id,
            event_type="conversation_share.created",
            resource_type="conversation_share",
            resource_id=share.id,
            conversation_id=conversation.id,
            payload={"include_artifacts": share.include_artifacts},
        )
        return share, token

    async def list_shares(
        self,
        db: AsyncSession,
        *,
        conversation_id: UUID,
        owner_user_id: UUID,
    ) -> list[ConversationShare]:
        stmt = (
            select(ConversationShare)
            .where(ConversationShare.conversation_id == conversation_id)
            .where(ConversationShare.owner_user_id == owner_user_id)
            .order_by(ConversationShare.created_at.desc())
        )
        return list((await db.execute(stmt)).scalars().all())

    async def revoke_share(
        self,
        db: AsyncSession,
        *,
        conversation_id: UUID,
        owner_user_id: UUID,
        share_id: UUID,
    ) -> ConversationShare:
        share = await db.get(ConversationShare, share_id)
        if (
            share is None
            or share.conversation_id != conversation_id
            or share.owner_user_id != owner_user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "SHARE_NOT_FOUND", "message": "Share not found"}},
            )
        share.revoked_at = datetime.now(UTC)
        await record_audit_event(
            db,
            user_id=owner_user_id,
            action="conversation_share.revoked",
            resource_type="conversation_share",
            resource_id=share.id,
            metadata={"conversation_id": str(conversation_id)},
        )
        await event_service.record(
            db,
            user_id=owner_user_id,
            event_type="conversation_share.revoked",
            resource_type="conversation_share",
            resource_id=share.id,
            conversation_id=conversation_id,
        )
        return share

    async def get_public_snapshot(
        self,
        db: AsyncSession,
        *,
        token: str,
    ) -> PublicConversationShareOut:
        share = await self._active_share_by_token(db, token)
        conversation = await db.get(Conversation, share.conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "SHARE_NOT_FOUND", "message": "Share not found"}},
            )
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .where(Message.role != "system")
            .order_by(Message.created_at.asc())
        )
        messages = list((await db.execute(stmt)).scalars().all())
        share.last_accessed_at = datetime.now(UTC)
        await record_audit_event(
            db,
            user_id=share.owner_user_id,
            action="conversation_share.accessed",
            resource_type="conversation_share",
            resource_id=share.id,
            metadata={"conversation_id": str(conversation.id)},
        )
        return PublicConversationShareOut(
            conversation_id=conversation.id,
            title=conversation.title,
            mode=conversation.mode,
            include_artifacts=share.include_artifacts,
            created_at=share.created_at,
            expires_at=share.expires_at,
            messages=[
                PublicSharedMessageOut(
                    id=message.id,
                    role=message.role,
                    agent_id=message.agent_id,
                    content=_safe_blocks(
                        message.content,
                        include_artifacts=share.include_artifacts,
                    ),
                    created_at=message.created_at,
                )
                for message in messages
            ],
        )

    async def _active_share_by_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> ConversationShare:
        token_hash = hash_refresh_token(token)
        stmt = select(ConversationShare).where(ConversationShare.token_hash == token_hash)
        share = (await db.execute(stmt)).scalar_one_or_none()
        now = datetime.now(UTC)
        if (
            share is None
            or share.revoked_at is not None
            or (share.expires_at is not None and share.expires_at <= now)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "SHARE_NOT_FOUND", "message": "Share not found"}},
            )
        return share

    def to_out(self, share: ConversationShare, token: str | None = None) -> ConversationShareOut:
        return ConversationShareOut(
            id=share.id,
            conversation_id=share.conversation_id,
            token=token,
            url_path=f"/share/{token}" if token else None,
            include_artifacts=share.include_artifacts,
            expires_at=share.expires_at,
            revoked_at=share.revoked_at,
            created_at=share.created_at,
            last_accessed_at=share.last_accessed_at,
        )


def _safe_blocks(blocks: list[dict[str, Any]], *, include_artifacts: bool) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    allowed_types = set(SAFE_BLOCK_TYPES)
    if include_artifacts:
        allowed_types |= ARTIFACT_BLOCK_TYPES
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type not in allowed_types:
            continue
        copied = dict(block)
        if block_type == "deployment_status" and not include_artifacts:
            copied.pop("download_url", None)
            copied.pop("logs_preview", None)
        if block_type == "file" and not include_artifacts:
            continue
        if block_type == "attachment" and not include_artifacts:
            continue
        safe.append(copied)
    return safe


conversation_share_service = ConversationShareService()
