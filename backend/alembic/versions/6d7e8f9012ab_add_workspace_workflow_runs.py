"""add workspace workflow run history.

Revision ID: 6d7e8f9012ab
Revises: 5c6d7e8f9012
Create Date: 2026-06-03 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d7e8f9012ab"
down_revision: str | None = "5c6d7e8f9012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workspace_workflow_runs" in set(inspector.get_table_names()):
        return
    op.create_table(
        "workspace_workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("runtime_status", sa.String(length=32), nullable=False),
        sa.Column("dry_run_status", sa.String(length=32), nullable=False),
        sa.Column("health_status", sa.String(length=32), nullable=False),
        sa.Column(
            "inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "definition",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "node_results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_workspace_workflow_runs_conversation_id",
        "workspace_workflow_runs",
        ["conversation_id"],
    )
    op.create_index(
        "idx_workspace_workflow_runs_workspace_id",
        "workspace_workflow_runs",
        ["workspace_id"],
    )
    op.create_index("idx_workspace_workflow_runs_path", "workspace_workflow_runs", ["path"])
    op.create_index(
        "idx_workspace_workflow_runs_status",
        "workspace_workflow_runs",
        ["status"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workspace_workflow_runs" not in set(inspector.get_table_names()):
        return
    op.drop_index("idx_workspace_workflow_runs_status", table_name="workspace_workflow_runs")
    op.drop_index("idx_workspace_workflow_runs_path", table_name="workspace_workflow_runs")
    op.drop_index(
        "idx_workspace_workflow_runs_workspace_id",
        table_name="workspace_workflow_runs",
    )
    op.drop_index(
        "idx_workspace_workflow_runs_conversation_id",
        table_name="workspace_workflow_runs",
    )
    op.drop_table("workspace_workflow_runs")
