"""Structured memory service for Orchestrator runs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
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
from app.services.artifact_metadata import classify_artifact

DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS = 3
DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS = 6000
DEFAULT_AGENT_CAPABILITY_PROFILE_RECENT_RUNS = 20
MAX_AGENT_CAPABILITY_PROFILE_RECENT_RUNS = 100
MAX_AGENT_FAILURE_REASONS = 5
MAX_TEXT_PREVIEW_CHARS = 4000
MAX_EVENT_PAYLOAD_TEXT_CHARS = 2000
TERMINAL_RUN_STATUSES = {"done", "error", "cancelled"}
FAILED_TASK_STATES = {"failed", "artifact_missing", "evaluation_failed"}


@dataclass(slots=True)
class AgentCapabilityProfileItem:
    agent_id: str
    runs_considered: int = 0
    task_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    artifact_missing_count: int = 0
    evaluation_failed_count: int = 0
    avg_attempts: float = 0.0
    artifact_kinds: dict[str, int] = field(default_factory=dict)
    review_outcomes: dict[str, int] = field(default_factory=dict)
    repair_success_count: int = 0
    recent_failure_reasons: list[str] = field(default_factory=list)
    confidence: str = "low"


@dataclass(slots=True)
class _AgentCapabilityAccumulator:
    agent_id: str
    run_ids: set[UUID] = field(default_factory=set)
    task_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    artifact_missing_count: int = 0
    evaluation_failed_count: int = 0
    attempt_count: int = 0
    artifact_kinds: Counter[str] = field(default_factory=Counter)
    review_outcomes: Counter[str] = field(default_factory=Counter)
    repair_success_count: int = 0
    recent_failure_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _EventAttemptInsight:
    agent_id: str | None
    attempt_index: int | None
    artifact_kinds: set[str]
    artifact_missing: bool
    evaluation_failed: bool
    failure_reasons: list[str]


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


async def build_agent_capability_profile(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    recent_runs: int = DEFAULT_AGENT_CAPABILITY_PROFILE_RECENT_RUNS,
) -> list[AgentCapabilityProfileItem]:
    """Aggregate recent per-agent Orchestrator outcomes for one conversation."""
    runs = await _recent_terminal_runs(db, conversation_id, limit=recent_runs)
    if not runs:
        return []

    run_ids = [run.id for run in runs]
    tasks = await _tasks_for_runs(db, run_ids)
    attempts_by_task = await _attempts_by_task(db, [task.id for task in tasks])
    events_by_task = await _task_result_events_by_task(db, run_ids)

    profiles: dict[str, _AgentCapabilityAccumulator] = {}
    artifact_kind_seen: set[tuple[str, UUID, str]] = set()
    artifact_missing_seen: set[tuple[str, UUID, int | str]] = set()
    evaluation_failed_seen: set[tuple[str, UUID, int | str]] = set()

    for task in tasks:
        attempts = attempts_by_task.get(task.id, [])
        participating_agents = _accumulate_task_participation(
            profiles,
            task,
            attempts,
            artifact_kind_seen=artifact_kind_seen,
            artifact_missing_seen=artifact_missing_seen,
            evaluation_failed_seen=evaluation_failed_seen,
        )

        for event in events_by_task.get((task.run_id, task.task_id), []):
            for insight in _event_attempt_insights(event):
                insight_agent = insight.agent_id or task.agent_id
                if insight_agent not in participating_agents:
                    continue
                insight_profile = _profile_accumulator(profiles, insight_agent)
                _accumulate_artifact_kinds(
                    insight_profile,
                    insight_agent,
                    task.id,
                    insight.artifact_kinds,
                    artifact_kind_seen,
                )
                event_key: int | str = (
                    insight.attempt_index
                    if insight.attempt_index is not None
                    else f"event:{event.id}"
                )
                if (
                    attempts or task.final_state != "artifact_missing"
                ) and insight.artifact_missing:
                    _accumulate_failure_event(
                        insight_profile,
                        (insight_agent, task.id, event_key),
                        artifact_missing_seen,
                        "artifact_missing_count",
                    )
                if (
                    attempts or task.final_state != "evaluation_failed"
                ) and insight.evaluation_failed:
                    _accumulate_failure_event(
                        insight_profile,
                        (insight_agent, task.id, event_key),
                        evaluation_failed_seen,
                        "evaluation_failed_count",
                    )
                for reason in insight.failure_reasons:
                    _accumulate_failure_reason(insight_profile, reason)

    return [
        _finalize_profile(profile)
        for profile in sorted(
            profiles.values(),
            key=lambda item: (-item.task_count, item.agent_id),
        )
        if profile.task_count or profile.attempt_count
    ]


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


def _profile_accumulator(
    profiles: dict[str, _AgentCapabilityAccumulator],
    agent_id: str,
) -> _AgentCapabilityAccumulator:
    profile = profiles.get(agent_id)
    if profile is None:
        profile = _AgentCapabilityAccumulator(agent_id=agent_id)
        profiles[agent_id] = profile
    return profile


def _accumulate_task_participation(
    profiles: dict[str, _AgentCapabilityAccumulator],
    task: OrchestratorTask,
    attempts: list[OrchestratorTaskAttempt],
    *,
    artifact_kind_seen: set[tuple[str, UUID, str]],
    artifact_missing_seen: set[tuple[str, UUID, int | str]],
    evaluation_failed_seen: set[tuple[str, UUID, int | str]],
) -> set[str]:
    attempts_by_agent: dict[str, list[OrchestratorTaskAttempt]] = {}
    for attempt in attempts:
        attempts_by_agent.setdefault(attempt.agent_id, []).append(attempt)

    if not attempts_by_agent:
        return _accumulate_legacy_task(profiles, task)

    participating_agents: set[str] = set()
    for agent_id, agent_attempts in attempts_by_agent.items():
        if not any(attempt.state not in {"pending", "skipped"} for attempt in agent_attempts):
            continue
        participating_agents.add(agent_id)
        profile = _profile_accumulator(profiles, agent_id)
        profile.run_ids.add(task.run_id)
        profile.task_count += 1
        profile.attempt_count += len(agent_attempts)
        final_attempt = agent_attempts[-1]
        if final_attempt.state == "succeeded":
            profile.success_count += 1
            if task.task_type == "repair":
                profile.repair_success_count += 1
        elif final_attempt.state in FAILED_TASK_STATES:
            profile.failure_count += 1

        final_review_outcome = next(
            (
                attempt.review_outcome
                for attempt in reversed(agent_attempts)
                if attempt.review_outcome
            ),
            None,
        )
        if final_review_outcome:
            profile.review_outcomes.update([final_review_outcome])

        for attempt in agent_attempts:
            _accumulate_artifact_kinds(
                profile,
                agent_id,
                task.id,
                {classify_artifact(path) for path in attempt.artifact_paths},
                artifact_kind_seen,
            )
            attempt_key = (agent_id, task.id, attempt.attempt_index)
            if attempt.missing_artifact_paths or attempt.state == "artifact_missing":
                _accumulate_failure_event(
                    profile,
                    attempt_key,
                    artifact_missing_seen,
                    "artifact_missing_count",
                )
            if attempt.state == "evaluation_failed":
                _accumulate_failure_event(
                    profile,
                    attempt_key,
                    evaluation_failed_seen,
                    "evaluation_failed_count",
                )
            _accumulate_failure_reason(profile, _attempt_failure_reason(attempt))
    return participating_agents


def _accumulate_legacy_task(
    profiles: dict[str, _AgentCapabilityAccumulator],
    task: OrchestratorTask,
) -> set[str]:
    if task.final_state in {"pending", "skipped"}:
        return set()
    profile = _profile_accumulator(profiles, task.agent_id)
    profile.run_ids.add(task.run_id)
    profile.task_count += 1
    if task.final_state == "succeeded":
        profile.success_count += 1
        if task.task_type == "repair":
            profile.repair_success_count += 1
    elif task.final_state in FAILED_TASK_STATES:
        profile.failure_count += 1
    if task.final_state == "artifact_missing":
        profile.artifact_missing_count += 1
    if task.final_state == "evaluation_failed":
        profile.evaluation_failed_count += 1
    _accumulate_failure_reason(
        profile,
        task.final_state if task.final_state in FAILED_TASK_STATES else None,
    )
    return {task.agent_id}


def _accumulate_artifact_kinds(
    profile: _AgentCapabilityAccumulator,
    agent_id: str,
    task_row_id: UUID,
    artifact_kinds: set[str],
    seen: set[tuple[str, UUID, str]],
) -> None:
    for artifact_kind in artifact_kinds:
        key = (agent_id, task_row_id, artifact_kind)
        if key in seen:
            continue
        seen.add(key)
        profile.artifact_kinds.update([artifact_kind])


def _accumulate_failure_event(
    profile: _AgentCapabilityAccumulator,
    key: tuple[str, UUID, int | str],
    seen: set[tuple[str, UUID, int | str]],
    field_name: str,
) -> None:
    if key in seen:
        return
    seen.add(key)
    setattr(profile, field_name, getattr(profile, field_name) + 1)


def _attempt_failure_reason(attempt: OrchestratorTaskAttempt) -> str | None:
    if attempt.error:
        return _single_line(attempt.error, 240)
    if attempt.missing_artifact_paths:
        return f"missing artifacts: {', '.join(attempt.missing_artifact_paths[:3])}"
    if attempt.state in FAILED_TASK_STATES:
        return attempt.state
    return None


def _event_attempt_insights(event: OrchestratorRunEvent) -> list[_EventAttemptInsight]:
    payload = event.payload if isinstance(event.payload, Mapping) else {}
    attempts = payload.get("attempts")
    if not isinstance(attempts, list):
        attempts = [payload]
    insights: list[_EventAttemptInsight] = []
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            continue
        artifact_kinds = _artifact_kinds_from_payload(attempt)
        evaluation_results = attempt.get("evaluation_results")
        failed_evaluations = _failed_evaluation_reasons(evaluation_results)
        raw_agent_id = attempt.get("agent_id") or event.agent_id
        agent_id = raw_agent_id if isinstance(raw_agent_id, str) else None
        raw_attempt_index = attempt.get("attempt_index")
        attempt_index = raw_attempt_index if isinstance(raw_attempt_index, int) else None
        state = attempt.get("state")
        missing_artifact_paths = attempt.get("missing_artifact_paths")
        artifact_missing = state == "artifact_missing" or bool(
            isinstance(missing_artifact_paths, list) and missing_artifact_paths
        )
        insights.append(
            _EventAttemptInsight(
                agent_id=agent_id,
                attempt_index=attempt_index,
                artifact_kinds=set(artifact_kinds),
                artifact_missing=artifact_missing,
                evaluation_failed=state == "evaluation_failed" or bool(failed_evaluations),
                failure_reasons=failed_evaluations,
            )
        )
    return insights


def _artifact_kinds_from_payload(value: Any) -> Counter[str]:
    kinds: Counter[str] = Counter()
    if isinstance(value, Mapping):
        artifact_kind = value.get("artifact_kind")
        if isinstance(artifact_kind, str) and artifact_kind:
            kinds.update([artifact_kind])
        raw_path = value.get("path")
        if isinstance(raw_path, str) and raw_path:
            kinds.update([classify_artifact(raw_path)])
        checked = value.get("checked_artifacts")
        if isinstance(checked, list):
            for path in checked:
                if isinstance(path, str) and path:
                    kinds.update([classify_artifact(path)])
        for key in ("artifact_paths", "artifacts", "entries", "items", "results"):
            nested = value.get(key)
            if nested is not None:
                kinds.update(_artifact_kinds_from_payload(nested))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                kinds.update([classify_artifact(item)])
            else:
                kinds.update(_artifact_kinds_from_payload(item))
    return kinds


def _failed_evaluation_reasons(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    reasons: list[str] = []
    for result in value:
        if not isinstance(result, Mapping) or result.get("status") != "failed":
            continue
        evaluator = str(result.get("evaluator") or "evaluation")
        issues = result.get("issues")
        if not isinstance(issues, list) or not issues:
            reasons.append(f"{evaluator}: failed")
            continue
        for issue in issues:
            if not isinstance(issue, Mapping):
                continue
            message = str(issue.get("message") or issue.get("code") or "failed")
            reasons.append(f"{evaluator}: {_single_line(message, 180)}")
    return reasons


def _accumulate_failure_reason(
    profile: _AgentCapabilityAccumulator,
    reason: str | None,
) -> None:
    if not reason or reason in profile.recent_failure_reasons:
        return
    if len(profile.recent_failure_reasons) >= MAX_AGENT_FAILURE_REASONS:
        return
    profile.recent_failure_reasons.append(reason)


def _finalize_profile(
    profile: _AgentCapabilityAccumulator,
) -> AgentCapabilityProfileItem:
    avg_attempts = (
        round(profile.attempt_count / profile.task_count, 2)
        if profile.task_count
        else 0.0
    )
    return AgentCapabilityProfileItem(
        agent_id=profile.agent_id,
        runs_considered=len(profile.run_ids),
        task_count=profile.task_count,
        success_count=profile.success_count,
        failure_count=profile.failure_count,
        artifact_missing_count=profile.artifact_missing_count,
        evaluation_failed_count=profile.evaluation_failed_count,
        avg_attempts=avg_attempts,
        artifact_kinds=dict(profile.artifact_kinds.most_common()),
        review_outcomes=dict(profile.review_outcomes.most_common()),
        repair_success_count=profile.repair_success_count,
        recent_failure_reasons=profile.recent_failure_reasons[:MAX_AGENT_FAILURE_REASONS],
        confidence=_profile_confidence(profile),
    )


def _profile_confidence(profile: _AgentCapabilityAccumulator) -> str:
    if profile.task_count >= 5 and len(profile.run_ids) >= 3:
        return "high"
    if profile.task_count >= 2 or len(profile.run_ids) >= 2:
        return "medium"
    return "low"


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

    sections: list[str] = []
    capability_profile = await build_agent_capability_profile(
        db,
        conversation_id,
        recent_runs=DEFAULT_AGENT_CAPABILITY_PROFILE_RECENT_RUNS,
    )
    profile_section = _format_agent_capability_profile(capability_profile)
    if profile_section:
        sections.append(profile_section)

    memory_lines: list[str] = ["Previous Orchestrator structured memory:", ""]
    for run in runs:
        formatted = await _format_run(db, run)
        if formatted:
            memory_lines.append(formatted)
    memory_section = "\n\n".join(memory_lines).strip()
    if memory_section != "Previous Orchestrator structured memory:":
        sections.append(memory_section)

    text = _truncate_preserving_edges("\n\n".join(sections).strip(), max_chars)
    if not text.strip():
        return None
    return ChatMessage(role="system", content=text)



def _format_agent_capability_profile(
    items: list[AgentCapabilityProfileItem],
) -> str:
    if not items:
        return ""
    lines = ["Agent capability profile from recent Orchestrator runs:"]
    for item in items:
        parts = [
            f"runs_considered={item.runs_considered}",
            f"task_count={item.task_count}",
            f"success_count={item.success_count}",
            f"failure_count={item.failure_count}",
            f"artifact_missing_count={item.artifact_missing_count}",
            f"evaluation_failed_count={item.evaluation_failed_count}",
            f"avg_attempts={item.avg_attempts}",
            f"repair_success_count={item.repair_success_count}",
            f"confidence={item.confidence}",
        ]
        lines.append(f"- @{item.agent_id}: " + "; ".join(parts))
        if item.artifact_kinds:
            lines.append(f"  artifact_kinds: {_format_counter(item.artifact_kinds)}")
        if item.review_outcomes:
            lines.append(f"  review_outcomes: {_format_counter(item.review_outcomes)}")
        if item.recent_failure_reasons:
            lines.append(
                "  recent_failure_reasons: "
                + " | ".join(item.recent_failure_reasons[:MAX_AGENT_FAILURE_REASONS])
            )
    return "\n".join(lines)



def _format_counter(values: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items())


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
        "task_type": task.task_type,
        "review_of": list(task.review_of),
        "handoff_reason": task.handoff_reason,
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
