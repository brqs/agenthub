"""Workspace API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def _default_preview_viewports() -> list[Literal["desktop", "mobile"]]:
    return ["desktop", "mobile"]


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
        default_factory=_default_preview_viewports
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


DeploymentKind = Literal["static_site", "source_zip", "container"]
DeploymentStatus = Literal[
    "queued",
    "publishing",
    "published",
    "failed",
    "stopped",
    "not_supported",
]


class WorkspaceDeploymentRequest(BaseModel):
    kind: DeploymentKind
    entry_path: str | None = Field(default=None, min_length=1, max_length=512)
    requested_port: int | None = Field(default=None, ge=1, le=65535)
    container_port: int | None = Field(default=None, ge=1, le=65535)
    health_path: str | None = Field(default=None, min_length=1, max_length=256)
    start_command: str | None = Field(default=None, max_length=512)


class WorkspaceDeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    workspace_id: UUID
    kind: DeploymentKind
    status: DeploymentStatus
    entry_path: str | None = None
    url: str | None = None
    download_url: str | None = None
    error: str | None = None
    logs: list[str] = Field(default_factory=list)
    size_bytes: int | None = None
    artifact_digest: str | None = None
    file_count: int | None = None
    published_at: datetime | None = None
    stopped_at: datetime | None = None
    expires_at: datetime | None = None
    runtime_id: str | None = None
    image_id: str | None = None
    container_id: str | None = None
    host_port: int | None = None
    container_port: int | None = None
    runtime_kind: str | None = None
    runtime_status: str | None = None
    healthcheck_url: str | None = None
    logs_tail: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkspaceDeploymentListResponse(BaseModel):
    items: list[WorkspaceDeploymentResponse]
