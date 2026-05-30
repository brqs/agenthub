"""add workspace preview sessions.

Revision ID: 1d2e3f4a5b6c
Revises: 9a1b2c3d4e5f
Create Date: 2026-05-30 18:30:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d2e3f4a5b6c"
down_revision: str | None = "9a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "workspace_preview_sessions" not in table_names:
        op.create_table(
            "workspace_preview_sessions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("conversation_id", sa.UUID(), nullable=False),
            sa.Column("workspace_id", sa.UUID(), nullable=False),
            sa.Column("entry_path", sa.String(length=512), nullable=False),
            sa.Column("port", sa.Integer(), nullable=False),
            sa.Column("pid", sa.Integer(), nullable=True),
            sa.Column("url", sa.String(length=1024), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
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
            sa.Column(
                "last_accessed_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "conversation_id",
                name="uq_workspace_preview_sessions_conversation_id",
            ),
        )

    indexes = {
        index["name"] for index in inspector.get_indexes("workspace_preview_sessions")
    }
    if "idx_workspace_preview_sessions_conversation_id" not in indexes:
        op.create_index(
            "idx_workspace_preview_sessions_conversation_id",
            "workspace_preview_sessions",
            ["conversation_id"],
            unique=False,
        )
    if "idx_workspace_preview_sessions_workspace_id" not in indexes:
        op.create_index(
            "idx_workspace_preview_sessions_workspace_id",
            "workspace_preview_sessions",
            ["workspace_id"],
            unique=False,
        )
    if "idx_workspace_preview_sessions_port" not in indexes:
        op.create_index(
            "idx_workspace_preview_sessions_port",
            "workspace_preview_sessions",
            ["port"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("idx_workspace_preview_sessions_port", table_name="workspace_preview_sessions")
    op.drop_index(
        "idx_workspace_preview_sessions_workspace_id",
        table_name="workspace_preview_sessions",
    )
    op.drop_index(
        "idx_workspace_preview_sessions_conversation_id",
        table_name="workspace_preview_sessions",
    )
    op.drop_table("workspace_preview_sessions")
