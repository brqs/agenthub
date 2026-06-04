"""Message schemas — ContentBlock union + Message DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CursorPagination


# ─── ContentBlock 联合类型 ───────────────────────────────────────
class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    agent_id: str | None = None
    text: str


class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    agent_id: str | None = None
    language: str
    code: str


class DiffBlock(BaseModel):
    type: Literal["diff"] = "diff"
    agent_id: str | None = None
    filename: str
    before: str
    after: str


class WebPreviewBlock(BaseModel):
    type: Literal["web_preview"] = "web_preview"
    agent_id: str | None = None
    url: str
    title: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None


class FileBlock(BaseModel):
    type: Literal["file"] = "file"
    agent_id: str | None = None
    path: str | None = None
    artifact_kind: Literal["document", "ppt", "image", "archive", "code", "workflow", "other"] = (
        "other"
    )
    filename: str
    url: str
    size: int
    mime_type: str
    preview_text: str | None = None
    preview_truncated: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeploymentStatusBlock(BaseModel):
    type: Literal["deployment_status"] = "deployment_status"
    agent_id: str | None = None
    deployment_id: str
    kind: Literal["static_site", "source_zip", "container"]
    status: Literal["queued", "publishing", "published", "failed", "stopped", "not_supported"]
    title: str | None = None
    url: str | None = None
    download_url: str | None = None
    error: str | None = None
    logs_preview: str | None = None
    size_bytes: int | None = None
    artifact_digest: str | None = None
    file_count: int | None = None
    published_at: str | None = None
    stopped_at: str | None = None
    expires_at: str | None = None
    runtime_kind: str | None = None
    runtime_status: str | None = None
    host_port: int | None = None
    container_port: int | None = None
    healthcheck_url: str | None = None

class WorkflowBlock(BaseModel):
    type: Literal["workflow"] = "workflow"
    agent_id: str | None = None
    last_run_id: UUID | None = None
    name: str | None = None
    path: str | None = None
    format: Literal["json", "yaml"] = "yaml"
    definition: dict[str, Any] = Field(default_factory=dict)
    raw_definition: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    validation_status: Literal["passed", "failed", "unknown"] = "unknown"
    runtime_status: Literal["ready", "invalid", "not_supported"] = "not_supported"
    dry_run_status: Literal["passed", "failed", "not_supported"] = "not_supported"
    health_status: Literal["passed", "failed", "unknown"] = "unknown"
    validation_errors: list[str] = Field(default_factory=list)


class TaskCardTask(BaseModel):
    id: str
    agent_id: str
    title: str
    status: Literal["pending", "running", "done", "error"]


class TaskCardBlock(BaseModel):
    type: Literal["task_card"] = "task_card"
    agent_id: str | None = None
    title: str
    tasks: list[TaskCardTask] = Field(default_factory=list)


class ToolCallBlock(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    agent_id: str | None = None
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "ok", "error"]
    output_preview: str | None = None
    output_truncated: bool | None = None
    error_code: str | None = None


ContentBlock = Annotated[
    TextBlock
    | CodeBlock
    | DiffBlock
    | WebPreviewBlock
    | FileBlock
    | DeploymentStatusBlock
    | WorkflowBlock
    | TaskCardBlock
    | ToolCallBlock,
    Field(discriminator="type"),
]


# ─── Message DTOs ────────────────────────────────────────────────
MessageRole = Literal["user", "agent", "system"]
MessageStatus = Literal["pending", "streaming", "done", "error"]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    agent_id: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    reply_to_id: UUID | None = None
    status: MessageStatus = "done"
    is_pinned: bool = False
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: list[ContentBlock] = Field(..., min_length=1)
    target_agent_id: str | None = None


class SendMessageResponse(BaseModel):
    user_message: MessageOut
    agent_message: MessageOut


class UpdateMessageRequest(BaseModel):
    is_pinned: bool | None = None


class MessageList(CursorPagination[MessageOut]):
    pass
