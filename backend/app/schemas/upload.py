"""Upload schemas for user-supplied conversation/workspace files."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

UploadPurpose = Literal[
    "message_attachment",
    "workspace_file",
    "workspace_import",
    "agent_knowledge",
    "agent_icon",
    "skill_package",
    "mcp_config",
]
UploadStatus = Literal["ready", "processing", "failed", "deleted"]
UploadSafetyStatus = Literal["pending", "passed", "blocked", "manual_review_required"]
UploadPreviewKind = Literal["image", "archive", "document", "text", "code", "unknown"]
ClientPlatform = Literal["web", "desktop", "ios", "android"]


class AttachmentPreview(BaseModel):
    kind: UploadPreviewKind = "unknown"
    url: str | None = None
    thumbnail_url: str | None = None
    text_preview: str | None = None
    truncated: bool = False
    entries_preview: list[str] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    page_count: int | None = None


class UploadOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    detected_content_type: str | None = None
    size_bytes: int
    sha256: str
    purpose: UploadPurpose
    status: UploadStatus
    client_platform: ClientPlatform = "web"
    safety_status: UploadSafetyStatus
    preview: AttachmentPreview | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class CreateUploadSessionRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", max_length=255)
    total_size_bytes: int = Field(gt=0)
    purpose: UploadPurpose = "message_attachment"
    conversation_id: UUID | None = None
    expected_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    client_platform: ClientPlatform = "web"
    part_size_bytes: int = Field(default=5_000_000, ge=256_000, le=20_000_000)


class UploadSessionOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    total_size_bytes: int
    expected_sha256: str | None = None
    client_platform: ClientPlatform
    part_size_bytes: int
    received_parts: list[int] = Field(default_factory=list)
    status: Literal["open", "completed", "cancelled", "failed", "expired"]
    upload_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class CompleteUploadSessionRequest(BaseModel):
    sha256: str | None = Field(default=None, min_length=64, max_length=64)


class CompleteUploadSessionResponse(BaseModel):
    session: UploadSessionOut
    upload: UploadOut
