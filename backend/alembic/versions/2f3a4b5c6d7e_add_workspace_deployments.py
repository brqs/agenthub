"""add workspace deployments.

Revision ID: 2f3a4b5c6d7e
Revises: 1d2e3f4a5b6c
Create Date: 2026-05-31 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f3a4b5c6d7e"
down_revision: str | None = "1d2e3f4a5b6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "workspace_deployments" not in table_names:
        op.create_table(
            "workspace_deployments",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("conversation_id", sa.UUID(), nullable=False),
            sa.Column("workspace_id", sa.UUID(), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("entry_path", sa.String(length=512), nullable=True),
            sa.Column("url", sa.String(length=1024), nullable=True),
            sa.Column("download_url", sa.String(length=1024), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "logs",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
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
                ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = {
        index["name"] for index in inspector.get_indexes("workspace_deployments")
    }
    for name, columns in (
        ("idx_workspace_deployments_conversation_id", ["conversation_id"]),
        ("idx_workspace_deployments_workspace_id", ["workspace_id"]),
        ("idx_workspace_deployments_kind", ["kind"]),
        ("idx_workspace_deployments_status", ["status"]),
    ):
        if name not in indexes:
            op.create_index(name, "workspace_deployments", columns, unique=False)


def downgrade() -> None:
    op.drop_index("idx_workspace_deployments_status", table_name="workspace_deployments")
    op.drop_index("idx_workspace_deployments_kind", table_name="workspace_deployments")
    op.drop_index(
        "idx_workspace_deployments_workspace_id",
        table_name="workspace_deployments",
    )
    op.drop_index(
        "idx_workspace_deployments_conversation_id",
        table_name="workspace_deployments",
    )
    op.drop_table("workspace_deployments")
