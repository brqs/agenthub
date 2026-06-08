"""add agent asset tables

Revision ID: c5d6e7f809ab
Revises: b6c7d8e9f012
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f809ab"
down_revision: str | None = "b6c7d8e9f012"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "agent_asset_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("usage", sa.String(length=32), nullable=True),
        sa.Column("skill_id", sa.String(length=96), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=True),
        sa.Column("description", sa.String(length=240), nullable=True),
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
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "upload_id", "kind", name="uq_agent_asset_binding_upload"),
        sa.UniqueConstraint("skill_id", name="uq_agent_asset_binding_skill_id"),
    )
    op.create_index(
        "idx_agent_asset_bindings_agent_kind",
        "agent_asset_bindings",
        ["agent_id", "kind", "status", "created_at"],
    )
    op.create_index(
        "idx_agent_asset_bindings_owner_time",
        "agent_asset_bindings",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        op.f("ix_agent_asset_bindings_owner_user_id"),
        "agent_asset_bindings",
        ["owner_user_id"],
    )

    op.create_table(
        "agent_asset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["agent_asset_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "binding_id",
            "version",
            name="uq_agent_asset_versions_binding_version",
        ),
    )
    op.create_index(
        "idx_agent_asset_versions_binding_time",
        "agent_asset_versions",
        ["binding_id", "created_at"],
    )

    op.create_table(
        "agent_asset_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["agent_asset_bindings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_agent_asset_usage_agent_time",
        "agent_asset_usage_events",
        ["agent_id", "created_at"],
    )
    op.create_index(
        "idx_agent_asset_usage_binding_time",
        "agent_asset_usage_events",
        ["binding_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_asset_usage_binding_time", table_name="agent_asset_usage_events")
    op.drop_index("idx_agent_asset_usage_agent_time", table_name="agent_asset_usage_events")
    op.drop_table("agent_asset_usage_events")
    op.drop_index("idx_agent_asset_versions_binding_time", table_name="agent_asset_versions")
    op.drop_table("agent_asset_versions")
    op.drop_index(op.f("ix_agent_asset_bindings_owner_user_id"), table_name="agent_asset_bindings")
    op.drop_index("idx_agent_asset_bindings_owner_time", table_name="agent_asset_bindings")
    op.drop_index("idx_agent_asset_bindings_agent_kind", table_name="agent_asset_bindings")
    op.drop_table("agent_asset_bindings")
