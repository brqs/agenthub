"""Message lifecycle helpers shared by message and stream routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.message import Message
from app.models.orchestrator_memory import OrchestratorRun

_ORCHESTRATOR_TERMINAL_STATUSES = {"done", "error", "interrupted", "cancelled"}


async def cleanup_stale_streaming_messages(db: AsyncSession) -> int:
    """Mark old pending/streaming agent messages as error.

    This prevents abandoned SSE streams from locking a conversation forever.
    """
    reconciled_count = await _reconcile_terminal_orchestrator_messages(db)
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
    return reconciled_count + len(stale_messages)


async def _reconcile_terminal_orchestrator_messages(db: AsyncSession) -> int:
    result = await db.execute(
        select(Message, OrchestratorRun)
        .join(OrchestratorRun, OrchestratorRun.agent_message_id == Message.id)
        .where(Message.role == "agent")
        .where(Message.status.in_(("pending", "streaming")))
        .where(OrchestratorRun.status.in_(_ORCHESTRATOR_TERMINAL_STATUSES))
    )
    rows = list(result.all())
    for message, run in rows:
        message.status = _message_status_for_run(run.status)
        if not message.content:
            message.content = [_terminal_orchestrator_text_block(run)]
    if rows:
        await db.commit()
    return len(rows)


def _message_status_for_run(run_status: str) -> str:
    if run_status == "done":
        return "done"
    if run_status == "interrupted":
        return "interrupted"
    return "error"


def _terminal_orchestrator_text_block(run: OrchestratorRun) -> dict[str, str]:
    text = run.final_summary.strip()
    if not text:
        if run.status == "done":
            text = (
                "Orchestrator run completed, but the client stream ended before "
                "the final response was persisted."
            )
        else:
            text = (
                "Orchestrator run ended before the final response was persisted. "
                "Please retry if needed."
            )
    return {"type": "text", "agent_id": "orchestrator", "text": text}
