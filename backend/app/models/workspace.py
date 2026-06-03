"""Workspace SQLAlchemy model."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Workspace(Base):
    """A per-conversation filesystem sandbox."""

    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    root_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkspacePreviewSession(Base):
    """Platform-managed static preview session for a conversation workspace."""

    __tablename__ = "workspace_preview_sessions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_path: Mapped[str] = mapped_column(String(512), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="starting")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    artifact_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkspaceDeployment(Base):
    """Platform-managed deployment or export record for workspace artifacts."""

    __tablename__ = "workspace_deployments"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entry_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    download_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_token: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    artifact_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    image_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    container_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    host_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    runtime_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    healthcheck_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logs_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def summary(self) -> dict[str, Any]:
        """Return a compact JSON-safe deployment summary."""
        return {
            "deployment_id": str(self.id),
            "kind": self.kind,
            "status": self.status,
            "entry_path": self.entry_path,
            "url": self.url,
            "download_url": self.download_url,
            "error": self.error,
            "logs_preview": "\n".join(self.logs[-5:]),
            "size_bytes": self.size_bytes,
            "artifact_digest": self.artifact_digest,
            "file_count": self.file_count,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "runtime_id": self.runtime_id,
            "image_id": self.image_id,
            "container_id": self.container_id,
            "host_port": self.host_port,
            "container_port": self.container_port,
            "runtime_kind": self.runtime_kind,
            "runtime_status": self.runtime_status,
            "healthcheck_url": self.healthcheck_url,
            "logs_tail": self.logs_tail,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
        }


class WorkspaceWorkflowRun(Base):
    """A no-side-effect workflow dry-run record for a workspace artifact."""

    __tablename__ = "workspace_workflow_runs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="dry_run")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    runtime_status: Mapped[str] = mapped_column(String(32), nullable=False)
    dry_run_status: Mapped[str] = mapped_column(String(32), nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    node_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
