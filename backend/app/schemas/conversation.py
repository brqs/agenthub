"""Conversation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OffsetPagination

ConversationMode = Literal["single", "group"]


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    mode: ConversationMode
    agent_ids: list[str] = Field(default_factory=list)
    is_pinned: bool = False
    is_archived: bool = False
    last_message_at: datetime
    last_message_preview: str | None = None
    created_at: datetime


class CreateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    mode: ConversationMode
    agent_ids: list[str] = Field(min_length=1)


class UpdateConversationRequest(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None
    is_archived: bool | None = None


class ConversationList(OffsetPagination[ConversationOut]):
    pass
