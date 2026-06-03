"""add orchestrator review metadata.

Revision ID: 5c6d7e8f9012
Revises: 4b5c6d7e8f90
Create Date: 2026-06-03 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c6d7e8f9012"
down_revision: str | None = "4b5c6d7e8f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    task_columns = _columns("orchestrator_tasks")
    if "task_type" not in task_columns:
        op.add_column(
            "orchestrator_tasks",
            sa.Column(
                "task_type",
                sa.String(length=32),
                server_default="implementation",
                nullable=False,
            ),
        )
    if "review_of" not in task_columns:
        op.add_column(
            "orchestrator_tasks",
            sa.Column(
                "review_of",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )
    if "handoff_reason" not in task_columns:
        op.add_column(
            "orchestrator_tasks",
            sa.Column("handoff_reason", sa.Text(), nullable=True),
        )

    attempt_columns = _columns("orchestrator_task_attempts")
    if "review_outcome" not in attempt_columns:
        op.add_column(
            "orchestrator_task_attempts",
            sa.Column("review_outcome", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    attempt_columns = _columns("orchestrator_task_attempts")
    if "review_outcome" in attempt_columns:
        op.drop_column("orchestrator_task_attempts", "review_outcome")

    task_columns = _columns("orchestrator_tasks")
    if "handoff_reason" in task_columns:
        op.drop_column("orchestrator_tasks", "handoff_reason")
    if "review_of" in task_columns:
        op.drop_column("orchestrator_tasks", "review_of")
    if "task_type" in task_columns:
        op.drop_column("orchestrator_tasks", "task_type")
