"""Message lifecycle helpers shared by message and stream routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.message import Message


async def cleanup_stale_streaming_messages(db: AsyncSession) -> int:
    """Mark old pending/streaming agent messages as error.

    This prevents abandoned SSE streams from locking a conversation forever.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.agent_stream_stale_seconds)
    result = await db.execute(
        select(Message)
        .where(Message.role == "agent")
        .where(Message.status.in_(("pending", "streaming")))
        .where(Message.created_at <= cutoff)
    )
    stale_messages = list(result.scalars().all())
    for stale in stale_messages:
        stale.status = "error"
        if not stale.content:
            stale.content = [
                {
                    "type": "text",
                    "text": "Agent stream expired before completion. Please retry.",
                }
            ]
    if stale_messages:
        await db.commit()
    return len(stale_messages)
