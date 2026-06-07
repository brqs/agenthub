"""add memory hub

Revision ID: a0b1c2d3e4f5
Revises: 9b0123cdef45
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "9b0123cdef45"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("container_tag", sa.String(length=192), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("normalized_key", sa.String(length=192), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_memory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["supersedes_memory_id"],
            ["memories.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_owner_user_id", "memories", ["owner_user_id"])
    op.create_index(
        "idx_memories_owner_status",
        "memories",
        ["owner_user_id", "status", "updated_at"],
    )
    op.create_index(
        "idx_memories_scope_status",
        "memories",
        ["scope_type", "scope_id", "status"],
    )
    op.create_index("idx_memories_container", "memories", ["container_tag", "status"])
    op.create_index(
        "idx_memories_normalized_key",
        "memories",
        ["owner_user_id", "normalized_key"],
    )

    op.create_table(
        "memory_mounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mount_reason", sa.String(length=128), nullable=False),
        sa.Column("rank_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_memory_mounts_conversation_time",
        "memory_mounts",
        ["conversation_id", "created_at"],
    )
    op.create_index("idx_memory_mounts_agent_message", "memory_mounts", ["agent_message_id"])
    op.create_index("idx_memory_mounts_memory", "memory_mounts", ["memory_id"])

    op.alter_column("memories", "importance", server_default=None)
    op.alter_column("memories", "confidence", server_default=None)
    op.alter_column("memories", "status", server_default=None)
    op.alter_column("memory_mounts", "rank_score", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_memory_mounts_memory", table_name="memory_mounts")
    op.drop_index("idx_memory_mounts_agent_message", table_name="memory_mounts")
    op.drop_index("idx_memory_mounts_conversation_time", table_name="memory_mounts")
    op.drop_table("memory_mounts")
    op.drop_index("idx_memories_normalized_key", table_name="memories")
    op.drop_index("idx_memories_container", table_name="memories")
    op.drop_index("idx_memories_scope_status", table_name="memories")
    op.drop_index("idx_memories_owner_status", table_name="memories")
    op.drop_index("ix_memories_owner_user_id", table_name="memories")
    op.drop_table("memories")
