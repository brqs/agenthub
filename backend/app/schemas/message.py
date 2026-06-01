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
    filename: str
    url: str
    size: int
    mime_type: str


class DeploymentStatusBlock(BaseModel):
    type: Literal["deployment_status"] = "deployment_status"
    deployment_id: str
    kind: Literal["static_site", "source_zip", "container"]
    status: Literal["publishing", "published", "failed", "stopped", "not_supported"]
    title: str | None = None
    url: str | None = None
    download_url: str | None = None
    error: str | None = None
    logs_preview: str | None = None
    size_bytes: int | None = None


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
