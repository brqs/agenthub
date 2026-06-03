"""Structured memory for Orchestrator runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrchestratorRun(Base):
    __tablename__ = "orchestrator_runs"
    __table_args__ = (
        Index("idx_orch_runs_conversation_time", "conversation_id", "created_at"),
        Index("idx_orch_runs_agent_message", "agent_message_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    user_request: Mapped[str] = mapped_column(Text, default="", nullable=False)
    plan_source: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    final_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OrchestratorTask(Base):
    __tablename__ = "orchestrator_tasks"
    __table_args__ = (
        Index("idx_orch_tasks_run", "run_id"),
        Index("uq_orch_tasks_run_task", "run_id", "task_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orchestrator_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    instruction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    depends_on: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    include_history: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    task_type: Mapped[str] = mapped_column(
        String(32), default="implementation", nullable=False
    )
    review_of: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    handoff_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_state: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OrchestratorTaskAttempt(Base):
    __tablename__ = "orchestrator_task_attempts"
    __table_args__ = (
        Index("idx_orch_attempts_run", "run_id"),
        Index("idx_orch_attempts_task_row", "task_row_id"),
        Index("uq_orch_attempts_task_index", "task_row_id", "attempt_index", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orchestrator_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_row_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orchestrator_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    text_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tool_summaries: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    artifact_paths: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    missing_artifact_paths: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    review_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OrchestratorRunEvent(Base):
    __tablename__ = "orchestrator_run_events"
    __table_args__ = (Index("idx_orch_events_run_time", "run_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orchestrator_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
