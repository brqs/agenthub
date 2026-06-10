"""archive deterministic rules-v1 memory pollution

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op


revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        r"""
        UPDATE memories AS memory
        SET
            status = 'archived',
            metadata = COALESCE(memory.metadata, '{}'::jsonb) || jsonb_build_object(
                'cleanup_reason', 'rules-v1-non-persistent-or-agent-output',
                'cleanup_previous_status', memory.status,
                'cleanup_at', CURRENT_TIMESTAMP
            )
        WHERE COALESCE(memory.metadata->>'extractor', '') = 'rules-v1'
          AND memory.status IN ('active', 'candidate')
          AND (
            EXISTS (
                SELECT 1
                FROM messages AS source_message
                WHERE source_message.id = memory.source_id
                  AND source_message.role = 'agent'
            )
            OR (
                memory.content ~* '^(帮我|请你|能不能|可不可以|麻烦|给我|改一下)'
                AND memory.content !~ '(请记住|记住：|以后默认|从今以后|我喜欢|我偏好|每次都|始终|永远)'
            )
            OR memory.content ~* '(正在处理|正在组织回复|execution summary|tool call|抱歉|对不起)'
            OR memory.content ~ '[?？]$'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE memories
        SET
            status = COALESCE(metadata->>'cleanup_previous_status', 'candidate'),
            metadata = metadata - 'cleanup_reason' - 'cleanup_previous_status' - 'cleanup_at'
        WHERE metadata->>'cleanup_reason' = 'rules-v1-non-persistent-or-agent-output'
        """
    )
