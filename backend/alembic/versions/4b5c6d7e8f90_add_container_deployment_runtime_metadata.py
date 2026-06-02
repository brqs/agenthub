"""add container deployment runtime metadata.

Revision ID: 4b5c6d7e8f90
Revises: 3a4b5c6d7e8f
Create Date: 2026-06-01 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b5c6d7e8f90"
down_revision: str | None = "3a4b5c6d7e8f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_deployments",
        sa.Column("runtime_id", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("image_id", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("container_id", sa.String(length=256), nullable=True),
    )
    op.add_column("workspace_deployments", sa.Column("host_port", sa.Integer(), nullable=True))
    op.add_column(
        "workspace_deployments",
        sa.Column("container_port", sa.Integer(), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("runtime_kind", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("runtime_status", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("healthcheck_url", sa.String(length=1024), nullable=True),
    )
    op.add_column("workspace_deployments", sa.Column("logs_tail", sa.Text(), nullable=True))
    op.add_column(
        "workspace_deployments",
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_deployments", "last_checked_at")
    op.drop_column("workspace_deployments", "completed_at")
    op.drop_column("workspace_deployments", "started_at")
    op.drop_column("workspace_deployments", "queued_at")
    op.drop_column("workspace_deployments", "logs_tail")
    op.drop_column("workspace_deployments", "healthcheck_url")
    op.drop_column("workspace_deployments", "runtime_status")
    op.drop_column("workspace_deployments", "runtime_kind")
    op.drop_column("workspace_deployments", "container_port")
    op.drop_column("workspace_deployments", "host_port")
    op.drop_column("workspace_deployments", "container_id")
    op.drop_column("workspace_deployments", "image_id")
    op.drop_column("workspace_deployments", "runtime_id")
