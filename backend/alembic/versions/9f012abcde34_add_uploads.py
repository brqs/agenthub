"""add uploads

Revision ID: 9f012abcde34
Revises: 8f9012abcde3
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f012abcde34"
down_revision: str | None = "8f9012abcde3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("detected_content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("safety_status", sa.String(length=32), nullable=False),
        sa.Column("preview", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
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
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_uploads_conversation_time", "uploads", ["conversation_id", "created_at"])
    op.create_index("idx_uploads_owner_time", "uploads", ["owner_user_id", "created_at"])
    op.create_index(op.f("ix_uploads_conversation_id"), "uploads", ["conversation_id"])
    op.create_index(op.f("ix_uploads_owner_user_id"), "uploads", ["owner_user_id"])

    op.create_table(
        "message_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "upload_id", name="uq_message_attachment"),
    )
    op.create_index("idx_message_attachments_message", "message_attachments", ["message_id"])
    op.create_index("idx_message_attachments_upload", "message_attachments", ["upload_id"])


def downgrade() -> None:
    op.drop_index("idx_message_attachments_upload", table_name="message_attachments")
    op.drop_index("idx_message_attachments_message", table_name="message_attachments")
    op.drop_table("message_attachments")
    op.drop_index(op.f("ix_uploads_owner_user_id"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_conversation_id"), table_name="uploads")
    op.drop_index("idx_uploads_owner_time", table_name="uploads")
    op.drop_index("idx_uploads_conversation_time", table_name="uploads")
    op.drop_table("uploads")
