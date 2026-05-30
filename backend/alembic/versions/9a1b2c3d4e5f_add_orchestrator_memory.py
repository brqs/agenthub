"""add orchestrator memory.

Revision ID: 9a1b2c3d4e5f
Revises: f4a3b2c1d0e9
Create Date: 2026-05-30 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1b2c3d4e5f"
down_revision: str | None = "f4a3b2c1d0e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_index_if_missing(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "orchestrator_runs" not in table_names:
        op.create_table(
            "orchestrator_runs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("conversation_id", sa.UUID(), nullable=False),
            sa.Column("agent_message_id", sa.UUID(), nullable=True),
            sa.Column("user_message_id", sa.UUID(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("user_request", sa.Text(), nullable=False),
            sa.Column("plan_source", sa.String(length=64), nullable=False),
            sa.Column("final_summary", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["agent_message_id"], ["messages.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["user_message_id"], ["messages.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "orchestrator_tasks" not in table_names:
        op.create_table(
            "orchestrator_tasks",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("run_id", sa.UUID(), nullable=False),
            sa.Column("task_id", sa.String(length=128), nullable=False),
            sa.Column("agent_id", sa.String(length=128), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("instruction", sa.Text(), nullable=False),
            sa.Column("depends_on", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("expected_output", sa.Text(), nullable=True),
            sa.Column("include_history", sa.Boolean(), nullable=False),
            sa.Column("final_state", sa.String(length=32), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["run_id"], ["orchestrator_runs.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "orchestrator_task_attempts" not in table_names:
        op.create_table(
            "orchestrator_task_attempts",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("run_id", sa.UUID(), nullable=False),
            sa.Column("task_row_id", sa.UUID(), nullable=False),
            sa.Column("task_id", sa.String(length=128), nullable=False),
            sa.Column("attempt_index", sa.Integer(), nullable=False),
            sa.Column("agent_id", sa.String(length=128), nullable=False),
            sa.Column("state", sa.String(length=32), nullable=False),
            sa.Column("text_preview", sa.Text(), nullable=False),
            sa.Column("tool_summaries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("artifact_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column(
                "missing_artifact_paths",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["run_id"], ["orchestrator_runs.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["task_row_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "orchestrator_run_events" not in table_names:
        op.create_table(
            "orchestrator_run_events",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("run_id", sa.UUID(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("task_id", sa.String(length=128), nullable=True),
            sa.Column("agent_id", sa.String(length=128), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["run_id"], ["orchestrator_runs.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "orchestrator_runs",
        "idx_orch_runs_conversation_time",
        ["conversation_id", "created_at"],
    )
    _create_index_if_missing(
        inspector,
        "orchestrator_runs",
        "idx_orch_runs_agent_message",
        ["agent_message_id"],
    )
    _create_index_if_missing(
        inspector,
        "orchestrator_tasks",
        "idx_orch_tasks_run",
        ["run_id"],
    )
    _create_index_if_missing(
        inspector,
        "orchestrator_tasks",
        "uq_orch_tasks_run_task",
        ["run_id", "task_id"],
        unique=True,
    )
    _create_index_if_missing(
        inspector,
        "orchestrator_task_attempts",
        "idx_orch_attempts_run",
        ["run_id"],
    )
    _create_index_if_missing(
        inspector,
        "orchestrator_task_attempts",
        "idx_orch_attempts_task_row",
        ["task_row_id"],
    )
    _create_index_if_missing(
        inspector,
        "orchestrator_task_attempts",
        "uq_orch_attempts_task_index",
        ["task_row_id", "attempt_index"],
        unique=True,
    )
    _create_index_if_missing(
        inspector,
        "orchestrator_run_events",
        "idx_orch_events_run_time",
        ["run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_orch_events_run_time", table_name="orchestrator_run_events")
    op.drop_index("uq_orch_attempts_task_index", table_name="orchestrator_task_attempts")
    op.drop_index("idx_orch_attempts_task_row", table_name="orchestrator_task_attempts")
    op.drop_index("idx_orch_attempts_run", table_name="orchestrator_task_attempts")
    op.drop_index("uq_orch_tasks_run_task", table_name="orchestrator_tasks")
    op.drop_index("idx_orch_tasks_run", table_name="orchestrator_tasks")
    op.drop_index("idx_orch_runs_agent_message", table_name="orchestrator_runs")
    op.drop_index("idx_orch_runs_conversation_time", table_name="orchestrator_runs")
    op.drop_table("orchestrator_run_events")
    op.drop_table("orchestrator_task_attempts")
    op.drop_table("orchestrator_tasks")
    op.drop_table("orchestrator_runs")
