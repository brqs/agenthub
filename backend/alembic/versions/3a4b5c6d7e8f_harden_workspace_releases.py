"""harden workspace preview and deployments.

Revision ID: 3a4b5c6d7e8f
Revises: 2f3a4b5c6d7e
Create Date: 2026-06-01 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a4b5c6d7e8f"
down_revision: str | None = "2f3a4b5c6d7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_preview_sessions",
        sa.Column("snapshot_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "workspace_preview_sessions",
        sa.Column("artifact_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("release_token", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("snapshot_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("artifact_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("file_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_deployments",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_workspace_deployments_release_token",
        "workspace_deployments",
        ["release_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_workspace_deployments_release_token", table_name="workspace_deployments")
    op.drop_column("workspace_deployments", "expires_at")
    op.drop_column("workspace_deployments", "stopped_at")
    op.drop_column("workspace_deployments", "published_at")
    op.drop_column("workspace_deployments", "file_count")
    op.drop_column("workspace_deployments", "artifact_digest")
    op.drop_column("workspace_deployments", "snapshot_path")
    op.drop_column("workspace_deployments", "release_token")
    op.drop_column("workspace_preview_sessions", "artifact_digest")
    op.drop_column("workspace_preview_sessions", "snapshot_path")
