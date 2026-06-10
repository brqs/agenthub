"""Local runtime connector schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LocalRuntimeConnectorStatusOut(BaseModel):
    enabled: bool
    deployment_mode: Literal["local", "hosted"]
    connectors: list[LocalRuntimeConnectorOut] = Field(default_factory=list)


class RegisterLocalRuntimeConnectorRequest(BaseModel):
    name: str = Field(default="AgentHub Desktop", min_length=1, max_length=160)
    endpoint_url: str = Field(min_length=1, max_length=512)
    bearer_token: str = Field(min_length=16, max_length=4096)
    runtime_ids: list[Literal["claude-code", "codex-helper", "opencode-helper"]] = Field(
        default_factory=list,
        max_length=8,
    )
    capabilities: dict = Field(default_factory=dict)
    expires_at: datetime | None = None


class LocalRuntimeConnectorOut(BaseModel):
    id: UUID
    name: str
    endpoint_url: str
    status: Literal["ready", "unavailable", "revoked"]
    runtime_ids: list[str] = Field(default_factory=list)
    capabilities: dict = Field(default_factory=dict)
    created_at: datetime
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_error: str | None = None


LocalRuntimeConnectorStatusOut.model_rebuild()
