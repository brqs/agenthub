"""add message queue entries

Revision ID: 8f9012abcde3
Revises: 7e8f9012abcd
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8f9012abcde3"
down_revision: str | None = "7e8f9012abcd"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "message_queue_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_agent_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("dispatched_agent_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["dispatched_agent_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_message_id", name="uq_message_queue_user_message"),
    )
    op.create_index(
        "idx_msg_queue_conv_state_time",
        "message_queue_entries",
        ["conversation_id", "state", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_queue_entries_conversation_id"),
        "message_queue_entries",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_message_queue_entries_conversation_id"), table_name="message_queue_entries")
    op.drop_index("idx_msg_queue_conv_state_time", table_name="message_queue_entries")
    op.drop_table("message_queue_entries")
