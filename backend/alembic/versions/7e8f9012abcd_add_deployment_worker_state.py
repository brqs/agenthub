"""add deployment worker state.

Revision ID: 7e8f9012abcd
Revises: 6d7e8f9012ab
Create Date: 2026-06-04 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7e8f9012abcd"
down_revision: str | None = "6d7e8f9012ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_deployments",
        sa.Column("worker_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("failure_category", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column(
            "state_events",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_deployments", "state_events")
    op.drop_column("workspace_deployments", "last_error_code")
    op.drop_column("workspace_deployments", "failure_category")
    op.drop_column("workspace_deployments", "attempt_count")
    op.drop_column("workspace_deployments", "worker_id")
