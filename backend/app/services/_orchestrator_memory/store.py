"""Persistence lifecycle for Orchestrator structured memory."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.evaluation import (
    evaluation_results_payload,
    reflection_payload,
)
from app.agents.orchestrator.types import SubTask, TaskResult
from app.models.orchestrator_memory import (
    OrchestratorRun,
    OrchestratorRunEvent,
    OrchestratorTask,
    OrchestratorTaskAttempt,
)
from app.services._orchestrator_memory.serialization import (
    _sanitize_json,
    _task_payload,
    _truncate_list,
    _truncate_text,
)
from app.services._orchestrator_memory.types import (
    MAX_EVENT_PAYLOAD_TEXT_CHARS,
    MAX_TEXT_PREVIEW_CHARS,
)


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
        task_row.task_type = task.task_type
        task_row.review_of = list(task.review_of)
        task_row.handoff_reason = task.handoff_reason
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
            row.review_outcome = _truncate_text(attempt.review_outcome, 32)
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
                        "review_outcome": attempt.review_outcome,
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
            task_type=task.task_type,
            review_of=list(task.review_of),
            handoff_reason=task.handoff_reason,
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
