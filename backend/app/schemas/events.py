"""Realtime user event schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cursor: int
    event_type: str
    resource_type: str
    resource_id: str
    conversation_id: UUID | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class UserEventList(BaseModel):
    items: list[UserEventOut]
    next_cursor: int | None = None
