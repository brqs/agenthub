"""Shared database queries for Orchestrator structured memory."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.orchestrator_memory import (
    OrchestratorRun,
    OrchestratorRunEvent,
    OrchestratorTask,
    OrchestratorTaskAttempt,
)
from app.services._orchestrator_memory.types import (
    MAX_AGENT_CAPABILITY_PROFILE_RECENT_RUNS,
    TERMINAL_RUN_STATUSES,
)


async def _recent_user_terminal_runs(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
) -> list[OrchestratorRun]:
    result = await db.execute(
        select(OrchestratorRun)
        .join(Conversation, Conversation.id == OrchestratorRun.conversation_id)
        .where(Conversation.user_id == user_id)
        .where(OrchestratorRun.status.in_(TERMINAL_RUN_STATUSES))
        .order_by(desc(OrchestratorRun.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def _conversation_user_id(db: AsyncSession, conversation_id: UUID) -> UUID | None:
    result = await db.execute(
        select(Conversation.user_id).where(Conversation.id == conversation_id)
    )
    return result.scalar_one_or_none()


async def _recent_terminal_runs(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    limit: int,
) -> list[OrchestratorRun]:
    limit = max(1, min(limit, MAX_AGENT_CAPABILITY_PROFILE_RECENT_RUNS))
    result = await db.execute(
        select(OrchestratorRun)
        .where(OrchestratorRun.conversation_id == conversation_id)
        .where(OrchestratorRun.status.in_(TERMINAL_RUN_STATUSES))
        .order_by(desc(OrchestratorRun.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def _tasks_for_runs(
    db: AsyncSession,
    run_ids: list[UUID],
) -> list[OrchestratorTask]:
    if not run_ids:
        return []
    result = await db.execute(
        select(OrchestratorTask)
        .where(OrchestratorTask.run_id.in_(run_ids))
        .order_by(desc(OrchestratorTask.created_at))
    )
    return list(result.scalars().all())


async def _tasks_for_run(
    db: AsyncSession,
    run_id: UUID,
) -> list[OrchestratorTask]:
    result = await db.execute(
        select(OrchestratorTask)
        .where(OrchestratorTask.run_id == run_id)
        .order_by(OrchestratorTask.priority.asc(), OrchestratorTask.created_at.asc())
    )
    return list(result.scalars().all())


async def _task_result_events_by_task(
    db: AsyncSession,
    run_ids: list[UUID],
) -> dict[tuple[UUID, str], list[OrchestratorRunEvent]]:
    if not run_ids:
        return {}
    result = await db.execute(
        select(OrchestratorRunEvent)
        .where(OrchestratorRunEvent.run_id.in_(run_ids))
        .where(OrchestratorRunEvent.event_type == "task_result")
        .order_by(desc(OrchestratorRunEvent.created_at))
    )
    grouped: dict[tuple[UUID, str], list[OrchestratorRunEvent]] = {}
    for event in result.scalars().all():
        if event.task_id:
            grouped.setdefault((event.run_id, event.task_id), []).append(event)
    return grouped


async def _attempts_for_run(
    db: AsyncSession,
    run_id: UUID,
) -> list[OrchestratorTaskAttempt]:
    result = await db.execute(
        select(OrchestratorTaskAttempt)
        .where(OrchestratorTaskAttempt.run_id == run_id)
        .order_by(
            OrchestratorTaskAttempt.task_id.asc(),
            OrchestratorTaskAttempt.attempt_index.asc(),
        )
    )
    return list(result.scalars().all())


async def _events_for_run(
    db: AsyncSession,
    run_id: UUID,
) -> list[OrchestratorRunEvent]:
    result = await db.execute(
        select(OrchestratorRunEvent)
        .where(OrchestratorRunEvent.run_id == run_id)
        .order_by(OrchestratorRunEvent.created_at.asc())
    )
    return list(result.scalars().all())


async def _attempts_by_task(
    db: AsyncSession,
    task_row_ids: list[UUID],
) -> dict[UUID, list[OrchestratorTaskAttempt]]:
    if not task_row_ids:
        return {}
    result = await db.execute(
        select(OrchestratorTaskAttempt)
        .where(OrchestratorTaskAttempt.task_row_id.in_(task_row_ids))
        .order_by(
            OrchestratorTaskAttempt.task_id.asc(),
            OrchestratorTaskAttempt.attempt_index.asc(),
        )
    )
    grouped: dict[UUID, list[OrchestratorTaskAttempt]] = {}
    for attempt in result.scalars().all():
        grouped.setdefault(attempt.task_row_id, []).append(attempt)
    return grouped
