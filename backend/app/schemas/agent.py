"""Agent schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OffsetPagination

AgentProvider = Literal[
    "claude_code",
    "codex",
    "opencode",
    "builtin",
    "mock",
    "claude",
    "deepseek",
    "openai",
    "custom",
]
CreatableAgentProvider = Literal["claude_code", "codex", "opencode", "builtin"]
ModelBackend = Literal["claude", "deepseek", "openai"]


class AgentConfig(BaseModel):
    model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for builtin agents.",
    )
    max_iterations: int | None = Field(default=None, ge=1, le=50)
    mcp_servers: list[dict[str, Any]] | None = None
    command: str | list[str] | None = None
    args: list[str] | None = None
    timeout_seconds: float | None = Field(default=None, ge=1, le=3600)

    # 允许额外 provider 专属字段
    model_config = ConfigDict(extra="allow")


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider: AgentProvider
    avatar_url: str = ""
    capabilities: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    is_builtin: bool = False
    created_at: datetime


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    provider: CreatableAgentProvider
    avatar_url: str = ""
    capabilities: list[str] = Field(default_factory=list, max_length=10)
    system_prompt: str | None = Field(default=None, max_length=8192)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    avatar_url: str | None = None
    capabilities: list[str] | None = Field(default=None, max_length=10)
    system_prompt: str | None = Field(default=None, max_length=8192)
    config: dict[str, Any] | None = None


class AgentList(OffsetPagination[AgentOut]):
    pass
