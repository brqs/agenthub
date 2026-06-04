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


ArtifactEvaluationStatus = Literal[
    "passed",
    "failed",
    "manual_review_required",
    "unknown",
]


class WorkspaceArtifactResponse(BaseModel):
    path: str
    artifact_kind: Literal[
        "document",
        "ppt",
        "image",
        "archive",
        "code",
        "workflow",
        "other",
    ]
    filename: str
    size: int
    mime_type: str
    url: str
    agent_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    preview_text: str | None = None
    preview_truncated: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    evaluation_status: ArtifactEvaluationStatus = "unknown"
    evaluation_results: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkspaceArtifactListResponse(BaseModel):
    items: list[WorkspaceArtifactResponse]


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
    worker_id: str | None = None
    attempt_count: int = 0
    failure_category: str | None = None
    last_error_code: str | None = None
    state_events: list[dict[str, Any]] = Field(default_factory=list)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkspaceDeploymentListResponse(BaseModel):
    items: list[WorkspaceDeploymentResponse]


WorkflowRunMode = Literal["dry_run"]
WorkflowRunStatus = Literal["passed", "failed"]
WorkflowValidationStatus = Literal["passed", "failed", "unknown"]
WorkflowRuntimeStatus = Literal["ready", "invalid", "not_supported"]
WorkflowDryRunStatus = Literal["passed", "failed", "not_supported"]
WorkflowHealthStatus = Literal["passed", "failed", "unknown"]


class WorkspaceWorkflowRunRequest(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    inputs: dict[str, Any] = Field(default_factory=dict)
    mode: WorkflowRunMode = "dry_run"


class WorkspaceWorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    workspace_id: UUID
    path: str
    mode: WorkflowRunMode
    status: WorkflowRunStatus
    validation_status: WorkflowValidationStatus
    runtime_status: WorkflowRuntimeStatus
    dry_run_status: WorkflowDryRunStatus
    health_status: WorkflowHealthStatus
    inputs: dict[str, Any] = Field(default_factory=dict)
    definition: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    node_results: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class WorkspaceWorkflowRunListResponse(BaseModel):
    items: list[WorkspaceWorkflowRunResponse]


class WorkspaceWorkflowHealthResponse(BaseModel):
    path: str
    validation_status: WorkflowValidationStatus
    runtime_status: WorkflowRuntimeStatus
    dry_run_status: WorkflowDryRunStatus
    health_status: WorkflowHealthStatus
    latest_run: WorkspaceWorkflowRunResponse | None = None
