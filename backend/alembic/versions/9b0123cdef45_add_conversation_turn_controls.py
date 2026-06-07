"""add conversation turn controls

Revision ID: 9b0123cdef45
Revises: 8f9012abcde3
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9b0123cdef45"
down_revision: str | None = "8f9012abcde3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "message_queue_entries",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY conversation_id
                    ORDER BY created_at ASC, id ASC
                ) - 1 AS next_position
            FROM message_queue_entries
            WHERE state = 'queued'
        )
        UPDATE message_queue_entries AS queue
        SET position = ranked.next_position
        FROM ranked
        WHERE queue.id = ranked.id
        """
    )
    op.alter_column("message_queue_entries", "position", server_default=None)
    op.drop_index("idx_msg_queue_conv_state_time", table_name="message_queue_entries")
    op.create_index(
        "idx_msg_queue_conv_state_position",
        "message_queue_entries",
        ["conversation_id", "state", "position", "created_at"],
        unique=False,
    )

    op.create_table(
        "conversation_turn_controls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_agent_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["active_agent_message_id"],
            ["messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_turn_controls_active_state",
        "conversation_turn_controls",
        ["active_agent_message_id", "state", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_turn_controls_conversation_time",
        "conversation_turn_controls",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_turn_controls_conversation_id"),
        "conversation_turn_controls",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_turn_controls_active_agent_message_id"),
        "conversation_turn_controls",
        ["active_agent_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_conversation_turn_controls_active_agent_message_id"),
        table_name="conversation_turn_controls",
    )
    op.drop_index(
        op.f("ix_conversation_turn_controls_conversation_id"),
        table_name="conversation_turn_controls",
    )
    op.drop_index(
        "idx_turn_controls_conversation_time",
        table_name="conversation_turn_controls",
    )
    op.drop_index("idx_turn_controls_active_state", table_name="conversation_turn_controls")
    op.drop_table("conversation_turn_controls")
    op.drop_index("idx_msg_queue_conv_state_position", table_name="message_queue_entries")
    op.create_index(
        "idx_msg_queue_conv_state_time",
        "message_queue_entries",
        ["conversation_id", "state", "created_at"],
        unique=False,
    )
    op.drop_column("message_queue_entries", "position")
