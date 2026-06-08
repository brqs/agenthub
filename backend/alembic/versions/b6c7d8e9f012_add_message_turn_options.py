"""add message turn options

Revision ID: b6c7d8e9f012
Revises: 9f012abcde34, a0b1c2d3e4f5
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f012"
down_revision: tuple[str, str] = ("9f012abcde34", "a0b1c2d3e4f5")
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "turn_options",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("messages", "turn_options", server_default=None)


def downgrade() -> None:
    op.drop_column("messages", "turn_options")
