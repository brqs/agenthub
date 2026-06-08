"""Schemas for MemoryHub semantic memories and dynamic mounts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MemoryScopeType = Literal["user", "conversation", "workspace", "agent", "group", "system"]
MemoryKind = Literal[
    "preference",
    "fact",
    "decision",
    "constraint",
    "project_context",
    "agent_profile",
    "artifact_note",
    "runtime_note",
]
MemoryImportance = Literal["critical", "high", "normal", "low"]
MemoryStatus = Literal["candidate", "active", "archived", "forgotten"]
MemorySourceType = Literal[
    "message",
    "orchestrator_run",
    "workspace_file",
    "upload",
    "manual",
]


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    scope_type: MemoryScopeType
    scope_id: UUID | None = None
    container_tag: str
    kind: MemoryKind
    content: str
    importance: MemoryImportance
    confidence: float
    status: MemoryStatus
    normalized_key: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    supersedes_memory_id: UUID | None = None
    source_type: MemorySourceType
    source_id: UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict, validation_alias="memory_metadata")
    created_at: datetime
    updated_at: datetime


class MemoryList(BaseModel):
    items: list[MemoryOut]
    total: int


class UpdateMemoryRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=8000)
    importance: MemoryImportance | None = None
    status: MemoryStatus | None = None
    kind: MemoryKind | None = None
    valid_until: datetime | None = None
    metadata: dict[str, object] | None = None


class MemoryMountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    agent_message_id: UUID | None = None
    memory_id: UUID
    mount_reason: str
    rank_score: float
    created_at: datetime
    memory: MemoryOut | None = None


class MemoryMountList(BaseModel):
    items: list[MemoryMountOut]
    total: int
