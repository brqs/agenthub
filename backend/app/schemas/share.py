"""Read-only conversation share schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationShareRequest(BaseModel):
    expires_at: datetime | None = None
    include_artifacts: bool = False


class ConversationShareOut(BaseModel):
    id: UUID
    conversation_id: UUID
    token: str | None = None
    url_path: str | None = None
    include_artifacts: bool
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    last_accessed_at: datetime | None = None


class PublicSharedMessageOut(BaseModel):
    id: UUID
    role: str
    agent_id: str | None = None
    content: list[dict] = Field(default_factory=list)
    created_at: datetime


class PublicConversationShareOut(BaseModel):
    conversation_id: UUID
    title: str
    mode: str
    include_artifacts: bool
    created_at: datetime
    expires_at: datetime | None = None
    messages: list[PublicSharedMessageOut] = Field(default_factory=list)
