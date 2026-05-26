"""Conversation-level compressed memory model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationMemory(Base):
    __tablename__ = "conversation_memories"
    __table_args__ = (Index("idx_conv_memory_conversation", "conversation_id"),)

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summarized_until_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_token_estimate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_token_estimate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(
        String(32), default="rules-v1", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
