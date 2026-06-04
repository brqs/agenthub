"""Run listing, detail loading, and context formatting."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestrator_memory import (
    OrchestratorRun,
    OrchestratorRunEvent,
    OrchestratorTask,
    OrchestratorTaskAttempt,
)
from app.services._orchestrator_memory.queries import (
    _attempts_by_task,
    _attempts_for_run,
    _events_for_run,
    _tasks_for_run,
)
from app.services._orchestrator_memory.serialization import _dedupe, _single_line


async def list_orchestrator_runs(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    limit: int = 20,
) -> list[OrchestratorRun]:
    limit = max(1, min(limit, 100))
    result = await db.execute(
        select(OrchestratorRun)
        .where(OrchestratorRun.conversation_id == conversation_id)
        .order_by(desc(OrchestratorRun.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_orchestrator_run_detail(
    db: AsyncSession,
    conversation_id: UUID,
    run_id: UUID,
) -> tuple[
    OrchestratorRun,
    list[OrchestratorTask],
    list[OrchestratorTaskAttempt],
    list[OrchestratorRunEvent],
] | None:
    run = await db.get(OrchestratorRun, run_id)
    if run is None or run.conversation_id != conversation_id:
        return None
    tasks = await _tasks_for_run(db, run_id)
    attempts = await _attempts_for_run(db, run_id)
    events = await _events_for_run(db, run_id)
    return run, tasks, attempts, events


async def _format_run(db: AsyncSession, run: OrchestratorRun) -> str:
    tasks = await _tasks_for_run(db, run.id)
    attempts_by_task = await _attempts_by_task(db, [task.id for task in tasks])
    created = run.created_at.isoformat() if run.created_at else ""
    lines = [
        f"Run {created} {run.status}",
        f"Request: {_single_line(run.user_request, 500)}",
    ]
    if run.final_summary:
        lines.append(f"Summary: {_single_line(run.final_summary, 700)}")
    for task in tasks:
        attempts = attempts_by_task.get(task.id, [])
        final_attempt = attempts[-1] if attempts else None
        agent_id = final_attempt.agent_id if final_attempt else task.agent_id
        lines.append(f"- {task.final_state} @{agent_id} {task.title}")
        artifacts = _dedupe(
            path for attempt in attempts for path in attempt.artifact_paths
        )
        missing = _dedupe(
            path for attempt in attempts for path in attempt.missing_artifact_paths
        )
        errors = [attempt.error for attempt in attempts if attempt.error]
        if artifacts:
            lines.append(f"  Artifacts: {', '.join(artifacts[:8])}")
        if missing:
            lines.append(f"  Missing: {', '.join(missing[:8])}")
        if final_attempt and final_attempt.text_preview:
            lines.append(f"  Text: {_single_line(final_attempt.text_preview, 700)}")
        if errors:
            lines.append(f"  Error: {_single_line(errors[-1] or '', 500)}")
    return "\n".join(lines)
