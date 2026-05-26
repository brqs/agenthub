"""add conversation memories.

Revision ID: c2f8e1d9a4b7
Revises: 829867f35d97
Create Date: 2026-05-25 20:55:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2f8e1d9a4b7"
down_revision: str | None = "829867f35d97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "conversation_memories" not in table_names:
        op.create_table(
            "conversation_memories",
            sa.Column("conversation_id", sa.UUID(), nullable=False),
            sa.Column("summary_text", sa.Text(), nullable=False),
            sa.Column("summarized_until_message_id", sa.UUID(), nullable=True),
            sa.Column("source_message_count", sa.Integer(), nullable=False),
            sa.Column("source_token_estimate", sa.Integer(), nullable=False),
            sa.Column("summary_token_estimate", sa.Integer(), nullable=False),
            sa.Column("algorithm_version", sa.String(length=32), nullable=False),
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
            sa.ForeignKeyConstraint(
                ["summarized_until_message_id"], ["messages.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("conversation_id"),
        )

    memory_indexes = {
        index["name"] for index in inspector.get_indexes("conversation_memories")
    }
    if "idx_conv_memory_conversation" not in memory_indexes:
        op.create_index(
            "idx_conv_memory_conversation",
            "conversation_memories",
            ["conversation_id"],
            unique=False,
        )

    message_indexes = {index["name"] for index in inspector.get_indexes("messages")}
    if "idx_msg_conv_pinned_time" not in message_indexes:
        op.create_index(
            "idx_msg_conv_pinned_time",
            "messages",
            ["conversation_id", "is_pinned", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("idx_msg_conv_pinned_time", table_name="messages")
    op.drop_index("idx_conv_memory_conversation", table_name="conversation_memories")
    op.drop_table("conversation_memories")
