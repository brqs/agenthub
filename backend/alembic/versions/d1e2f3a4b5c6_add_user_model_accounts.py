"""add user model accounts

Revision ID: d1e2f3a4b5c6
Revises: c5d6e7f809ab
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c5d6e7f809ab"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("user_model_accounts"):
        op.create_table(
            "user_model_accounts",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("protocol", sa.String(length=32), nullable=False),
            sa.Column("model", sa.String(length=160), nullable=False),
            sa.Column("base_url", sa.String(length=512), nullable=True),
            sa.Column("encrypted_api_key", sa.Text(), nullable=False),
            sa.Column("api_key_preview", sa.String(length=24), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(length=512), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        inspector = sa.inspect(bind)
    else:
        required_columns = {
            "id",
            "user_id",
            "display_name",
            "provider",
            "protocol",
            "model",
            "base_url",
            "encrypted_api_key",
            "api_key_preview",
            "status",
            "last_verified_at",
            "last_error",
            "created_at",
            "updated_at",
        }
        existing_columns = {
            column["name"] for column in inspector.get_columns("user_model_accounts")
        }
        missing_columns = sorted(required_columns - existing_columns)
        if missing_columns:
            raise RuntimeError(
                "Existing user_model_accounts table is incomplete; missing columns: "
                + ", ".join(missing_columns)
            )

    indexes = {index["name"] for index in inspector.get_indexes("user_model_accounts")}
    if "idx_user_model_accounts_user_provider" not in indexes:
        op.create_index(
            "idx_user_model_accounts_user_provider",
            "user_model_accounts",
            ["user_id", "provider"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("idx_user_model_accounts_user_provider", table_name="user_model_accounts")
    op.drop_table("user_model_accounts")
