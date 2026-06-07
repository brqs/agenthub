"""Upload schemas for user-supplied conversation/workspace files."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


UploadPurpose = Literal["message_attachment", "workspace_file"]
UploadStatus = Literal["ready", "processing", "failed", "deleted"]
UploadSafetyStatus = Literal["pending", "passed", "blocked", "manual_review_required"]
UploadPreviewKind = Literal["image", "archive", "document", "text", "code", "unknown"]


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
    safety_status: UploadSafetyStatus
    preview: AttachmentPreview | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
