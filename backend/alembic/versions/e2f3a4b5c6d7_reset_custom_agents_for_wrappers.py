"""reset custom agents for server wrappers

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH old_agents AS (
            SELECT id FROM agents WHERE is_builtin = false
        )
        UPDATE conversations
        SET agent_ids = COALESCE(
            (
                SELECT jsonb_agg(item)
                FROM jsonb_array_elements_text(conversations.agent_ids) AS item
                WHERE item NOT IN (SELECT id FROM old_agents)
            ),
            '[]'::jsonb
        )
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(conversations.agent_ids) AS item
            WHERE item IN (SELECT id FROM old_agents)
        )
        """
    )
    op.execute(
        """
        DELETE FROM agent_asset_usage_events
        WHERE agent_id IN (SELECT id FROM agents WHERE is_builtin = false)
        """
    )
    op.execute(
        """
        DELETE FROM agent_asset_versions
        WHERE binding_id IN (
            SELECT id
            FROM agent_asset_bindings
            WHERE agent_id IN (SELECT id FROM agents WHERE is_builtin = false)
        )
        """
    )
    op.execute(
        """
        DELETE FROM agent_asset_bindings
        WHERE agent_id IN (SELECT id FROM agents WHERE is_builtin = false)
        """
    )
    op.execute("DELETE FROM agents WHERE is_builtin = false")
    op.execute("DELETE FROM user_model_accounts")


def downgrade() -> None:
    # The deleted legacy custom Agent rows and user model accounts are intentionally
    # not reconstructable. The source uploads remain in the uploads table.
    return
