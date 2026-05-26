"""add workspaces.

Revision ID: f4a3b2c1d0e9
Revises: c2f8e1d9a4b7
Create Date: 2026-05-26 13:10:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a3b2c1d0e9"
down_revision: str | None = "c2f8e1d9a4b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "workspaces" not in table_names:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("conversation_id", sa.UUID(), nullable=False),
            sa.Column("root_path", sa.String(length=512), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "last_accessed_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("conversation_id", name="uq_workspaces_conversation_id"),
        )

    workspace_indexes = {index["name"] for index in inspector.get_indexes("workspaces")}
    if "idx_workspaces_conversation_id" not in workspace_indexes:
        op.create_index(
            "idx_workspaces_conversation_id",
            "workspaces",
            ["conversation_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("idx_workspaces_conversation_id", table_name="workspaces")
    op.drop_table("workspaces")
