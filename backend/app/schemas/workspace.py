"""Workspace API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceTreeNode(BaseModel):
    name: str
    path: str
    type: Literal["directory", "file"]
    children: list[WorkspaceTreeNode] = Field(default_factory=list)
    size: int | None = None
    mime_type: str | None = None


class WorkspaceTreeResponse(BaseModel):
    root: str
    tree: WorkspaceTreeNode


class WorkspacePreviewRequest(BaseModel):
    entry_path: str = Field(min_length=1, max_length=512)
    mode: Literal["static"] = "static"
    requested_port: int | None = Field(default=None, ge=1, le=65535)


class WorkspacePreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    workspace_id: UUID
    entry_path: str
    mode: Literal["static"] = "static"
    port: int
    pid: int | None = None
    url: str
    status: Literal["starting", "running", "stopped", "error"]
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime


class WorkspacePreviewVerifyRequest(BaseModel):
    required_text: list[str] = Field(default_factory=list)
    viewports: list[Literal["desktop", "mobile"]] = Field(
        default_factory=lambda: ["desktop", "mobile"]
    )
    click_buttons: bool = True
    max_clicks: int = Field(default=5, ge=0, le=10)


class WorkspacePreviewVerifyResponse(BaseModel):
    passed: bool
    checks: dict[str, bool]
    issues: list[dict[str, Any]]
    screenshots: dict[str, str]
    console_errors: list[str]
    page_errors: list[str]
    failed_requests: list[str]
    duration_ms: int
    report_path: str | None = None
