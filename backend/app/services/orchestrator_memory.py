"""Structured memory service for Orchestrator runs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.evaluation import (
    evaluation_results_payload,
    reflection_payload,
)
from app.agents.orchestrator.types import SubTask, TaskResult
from app.agents.types import ChatMessage
from app.models.orchestrator_memory import (
    OrchestratorRun,
    OrchestratorRunEvent,
    OrchestratorTask,
    OrchestratorTaskAttempt,
)

DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS = 3
DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS = 6000
MAX_TEXT_PREVIEW_CHARS = 4000
MAX_EVENT_PAYLOAD_TEXT_CHARS = 2000
TERMINAL_RUN_STATUSES = {"done", "error", "cancelled"}


class OrchestratorMemoryStore:
    """DB-backed writer/reader for Orchestrator structured memory."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        conversation_id: UUID,
        agent_message_id: UUID | None,
        user_message_id: UUID | None,
    ) -> None:
        self._db = db
        self._conversation_id = conversation_id
        self._agent_message_id = agent_message_id
        self._user_message_id = user_message_id
        self._active_run_id: UUID | None = None
        self._runs: dict[UUID, OrchestratorRun] = {}
        self._task_rows: dict[tuple[UUID, str], OrchestratorTask] = {}

    async def start_run(
        self,
        *,
        user_request: str,
        plan_source: str,
        tasks: list[SubTask],
    ) -> UUID:
        run = OrchestratorRun(
            id=uuid4(),
            conversation_id=self._conversation_id,
            agent_message_id=self._agent_message_id,
            user_message_id=self._user_message_id,
            status="running",
            user_request=_truncate_text(user_request, 16000),
            plan_source=_truncate_text(plan_source, 64),
            final_summary="",
        )
        self._db.add(run)
        self._active_run_id = run.id
        self._runs[run.id] = run
        for task in tasks:
            await self.record_task_planned(run_id=run.id, task=task)
        await self.record_event(
            run_id=run.id,
            event_type="planned",
            payload={
                "plan_source": plan_source,
                "task_count": len(tasks),
                "tasks": [_task_payload(task) for task in tasks],
            },
        )
        return run.id

    async def record_task_planned(
        self,
        *,
        run_id: UUID,
        task: SubTask,
    ) -> None:
        self._task_row(run_id, task)

    async def record_task_started(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        agent_id: str,
        attempt_index: int,
    ) -> None:
        self._task_row(run_id, task)
        await self.record_event(
            run_id=run_id,
            event_type="task_started",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "title": task.title,
                "attempt_index": attempt_index,
            },
        )

    async def record_task_result(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        result: TaskResult,
    ) -> None:
        task_row = self._task_row(run_id, task)
        task_row.agent_id = task.agent_id
        task_row.title = task.title
        task_row.instruction = task.instruction
        task_row.depends_on = list(task.depends_on)
        task_row.priority = task.priority
        task_row.expected_output = task.expected_output
        task_row.include_history = task.include_history
        task_row.final_state = result.final_state.value
        task_row.updated_at = datetime.now(UTC)

        existing = await self._attempts_by_index(task_row.id)
        for attempt in result.attempts:
            row = existing.get(attempt.attempt_index)
            if row is None:
                row = OrchestratorTaskAttempt(
                    id=uuid4(),
                    run_id=run_id,
                    task_row_id=task_row.id,
                    task_id=task.task_id,
                    attempt_index=attempt.attempt_index,
                    agent_id=attempt.agent_id,
                    state=attempt.state.value,
                    text_preview="",
                    tool_summaries=[],
                    artifact_paths=[],
                    missing_artifact_paths=[],
                )
                self._db.add(row)
            row.agent_id = attempt.agent_id
            row.state = attempt.state.value
            row.text_preview = (
                _truncate_text(attempt.text_preview, MAX_TEXT_PREVIEW_CHARS) or ""
            )
            row.tool_summaries = _truncate_list(attempt.tool_summaries)
            row.artifact_paths = _truncate_list(attempt.artifact_paths)
            row.missing_artifact_paths = _truncate_list(attempt.missing_artifact_paths)
            row.error = _truncate_text(attempt.error, MAX_TEXT_PREVIEW_CHARS)
            row.completed_at = datetime.now(UTC)

        await self.record_event(
            run_id=run_id,
            event_type="task_result",
            task_id=task.task_id,
            agent_id=result.attempts[-1].agent_id if result.attempts else task.agent_id,
            payload={
                "final_state": result.final_state.value,
                "attempts": [
                    {
                        "attempt_index": attempt.attempt_index,
                        "agent_id": attempt.agent_id,
                        "state": attempt.state.value,
                        "artifact_paths": attempt.artifact_paths,
                        "missing_artifact_paths": attempt.missing_artifact_paths,
                        "file_changes": attempt.file_changes,
                        "conflict_paths": attempt.conflict_paths,
                        "evaluation_results": evaluation_results_payload(
                            attempt.evaluation_results
                        ),
                        "reflection": reflection_payload(attempt.reflection),
                        "error": attempt.error,
                    }
                    for attempt in result.attempts
                ],
                "workspace_conflicts": result.workspace_conflicts,
            },
        )

    async def record_event(
        self,
        *,
        run_id: UUID,
        event_type: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._db.add(
            OrchestratorRunEvent(
                id=uuid4(),
                run_id=run_id,
                event_type=event_type,
                task_id=task_id,
                agent_id=agent_id,
                payload=_sanitize_json(payload or {}, MAX_EVENT_PAYLOAD_TEXT_CHARS),
            )
        )

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        final_summary: str,
    ) -> None:
        run = self._runs.get(run_id) or await self._db.get(OrchestratorRun, run_id)
        if run is None:
            return
        run.status = status
        run.final_summary = _truncate_text(final_summary, 32000) or ""
        run.completed_at = datetime.now(UTC)
        run.updated_at = datetime.now(UTC)
        await self.record_event(
            run_id=run_id,
            event_type="finished" if status == "done" else status,
            payload={"status": status, "final_summary": run.final_summary},
        )
        if self._active_run_id == run_id:
            self._active_run_id = None

    async def cancel_active_run(self) -> None:
        if self._active_run_id is None:
            return
        await self.finish_run(
            run_id=self._active_run_id,
            status="cancelled",
            final_summary="Stream disconnected before Orchestrator finished.",
        )

    def _task_row(self, run_id: UUID, task: SubTask) -> OrchestratorTask:
        key = (run_id, task.task_id)
        row = self._task_rows.get(key)
        if row is not None:
            return row
        row = OrchestratorTask(
            id=uuid4(),
            run_id=run_id,
            task_id=task.task_id,
            agent_id=task.agent_id,
            title=task.title,
            instruction=task.instruction,
            depends_on=list(task.depends_on),
            priority=task.priority,
            expected_output=task.expected_output,
            include_history=task.include_history,
            final_state="pending",
        )
        self._db.add(row)
        self._task_rows[key] = row
        return row

    async def _attempts_by_index(
        self,
        task_row_id: UUID,
    ) -> dict[int, OrchestratorTaskAttempt]:
        result = await self._db.execute(
            select(OrchestratorTaskAttempt).where(
                OrchestratorTaskAttempt.task_row_id == task_row_id
            )
        )
        return {attempt.attempt_index: attempt for attempt in result.scalars().all()}


async def build_orchestrator_memory_context(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    recent_runs: int = DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS,
    max_chars: int = DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS,
) -> ChatMessage | None:
    """Build a system message containing recent structured Orchestrator memory."""
    recent_runs = max(1, min(recent_runs, 10))
    max_chars = max(1, min(max_chars, 32000))
    result = await db.execute(
        select(OrchestratorRun)
        .where(OrchestratorRun.conversation_id == conversation_id)
        .where(OrchestratorRun.status.in_(TERMINAL_RUN_STATUSES))
        .order_by(desc(OrchestratorRun.created_at))
        .limit(recent_runs)
    )
    runs = list(reversed(result.scalars().all()))
    if not runs:
        return None

    sections: list[str] = ["Previous Orchestrator structured memory:", ""]
    for run in runs:
        formatted = await _format_run(db, run)
        if formatted:
            sections.append(formatted)
    text = _truncate_preserving_edges("\n\n".join(sections).strip(), max_chars)
    if not text.strip() or text.strip() == "Previous Orchestrator structured memory:":
        return None
    return ChatMessage(role="system", content=text)


def inject_orchestrator_memory_context(
    messages: list[ChatMessage],
    memory_message: ChatMessage | None,
) -> list[ChatMessage]:
    """Insert structured memory before the latest active user request."""
    if memory_message is None:
        return messages
    output = list(messages)
    for index in range(len(output) - 1, -1, -1):
        if output[index].role == "user":
            output.insert(index, memory_message)
            return output
    output.append(memory_message)
    return output


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
    tasks = list(
        (
            await db.execute(
                select(OrchestratorTask)
                .where(OrchestratorTask.run_id == run_id)
                .order_by(OrchestratorTask.priority.asc(), OrchestratorTask.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    attempts = list(
        (
            await db.execute(
                select(OrchestratorTaskAttempt)
                .where(OrchestratorTaskAttempt.run_id == run_id)
                .order_by(
                    OrchestratorTaskAttempt.task_id.asc(),
                    OrchestratorTaskAttempt.attempt_index.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    events = list(
        (
            await db.execute(
                select(OrchestratorRunEvent)
                .where(OrchestratorRunEvent.run_id == run_id)
                .order_by(OrchestratorRunEvent.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return run, tasks, attempts, events


async def _format_run(db: AsyncSession, run: OrchestratorRun) -> str:
    tasks = list(
        (
            await db.execute(
                select(OrchestratorTask)
                .where(OrchestratorTask.run_id == run.id)
                .order_by(OrchestratorTask.priority.asc(), OrchestratorTask.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
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


def _task_payload(task: SubTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "agent_id": task.agent_id,
        "title": task.title,
        "depends_on": list(task.depends_on),
        "priority": task.priority,
        "expected_output": task.expected_output,
        "include_history": task.include_history,
    }


def _truncate_list(values: Iterable[str], *, max_items: int = 50) -> list[str]:
    return [_truncate_text(value, 1000) or "" for value in list(values)[:max_items]]


def _sanitize_json(value: Any, max_text_chars: int) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, max_text_chars)
    if isinstance(value, Mapping):
        return {str(key): _sanitize_json(item, max_text_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item, max_text_chars) for item in value[:100]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _truncate_text(str(value), max_text_chars)


def _truncate_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _truncate_preserving_edges(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 64:
        return text[:max_chars]
    head = max_chars // 2
    tail = max_chars - head - len("\n...[truncated]...\n")
    return f"{text[:head]}\n...[truncated]...\n{text[-tail:]}"


def _single_line(text: str, max_chars: int) -> str:
    return (_truncate_text(" ".join(text.split()), max_chars) or "").strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
