"""Conversation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OffsetPagination

ConversationMode = Literal["single", "group"]
CompressionProvider = Literal[
    "deepseek",
    "openai",
    "openai_compatible",
    "anthropic",
    "claude",
]


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


class ConversationMemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: UUID
    summary_text: str
    summarized_until_message_id: UUID | None = None
    source_message_count: int
    source_token_estimate: int
    summary_token_estimate: int
    algorithm_version: str
    created_at: datetime
    updated_at: datetime


class OrchestratorTaskAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    task_row_id: UUID
    task_id: str
    attempt_index: int
    agent_id: str
    state: str
    text_preview: str
    tool_summaries: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    missing_artifact_paths: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class OrchestratorTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    task_id: str
    agent_id: str
    title: str
    instruction: str
    depends_on: list[str] = Field(default_factory=list)
    priority: int
    expected_output: str | None = None
    include_history: bool
    final_state: str
    created_at: datetime
    updated_at: datetime


class OrchestratorRunEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    event_type: str
    task_id: str | None = None
    agent_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class OrchestratorRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    agent_message_id: UUID | None = None
    user_message_id: UUID | None = None
    status: str
    user_request: str
    plan_source: str
    final_summary: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class OrchestratorRunList(BaseModel):
    items: list[OrchestratorRunOut]
    total: int


class OrchestratorRunDetailOut(BaseModel):
    run: OrchestratorRunOut
    tasks: list[OrchestratorTaskOut]
    attempts: list[OrchestratorTaskAttemptOut]
    events: list[OrchestratorRunEventOut]


class ContextCompressionConfigOut(BaseModel):
    mode: str
    provider: str
    model: str
    summary_max_tokens: int
    recent_raw_keep: int
    api_key_configured: bool
    api_key_source: str
    api_key_preview: str | None = None
    base_url: str
    supported_models: list[str]


class UpdateContextCompressionConfigRequest(BaseModel):
    mode: Literal["hybrid", "rules"] | None = None
    provider: CompressionProvider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=100)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    base_url: str | None = Field(default=None, max_length=2048)
    summary_max_tokens: int | None = Field(default=None, ge=256, le=8192)
    recent_raw_keep: int | None = Field(default=None, ge=1, le=100)


class ContextCompressionTestRequest(BaseModel):
    provider: CompressionProvider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=100)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    base_url: str | None = Field(default=None, max_length=2048)


class ContextCompressionTestOut(BaseModel):
    ok: bool
    provider: str
    model: str
    error_code: str | None = None
    message: str | None = None


class ConversationList(OffsetPagination[ConversationOut]):
    pass
