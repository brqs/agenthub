"""Conversation-scoped Agent Capability Profile v1 aggregation."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestrator_memory import (
    OrchestratorRunEvent,
    OrchestratorTask,
    OrchestratorTaskAttempt,
)
from app.services._orchestrator_memory.queries import (
    _attempts_by_task,
    _recent_terminal_runs,
    _task_result_events_by_task,
    _tasks_for_runs,
)
from app.services._orchestrator_memory.serialization import _single_line
from app.services._orchestrator_memory.types import (
    DEFAULT_AGENT_CAPABILITY_PROFILE_RECENT_RUNS,
    FAILED_TASK_STATES,
    MAX_AGENT_FAILURE_REASONS,
    AgentCapabilityProfileItem,
    _AgentCapabilityAccumulator,
    _EventAttemptInsight,
)
from app.services.artifacts.metadata import classify_artifact


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

        _accumulate_task_event_insights(
            task,
            attempts,
            events_by_task.get((task.run_id, task.task_id), []),
            participating_agents,
            profile_for_agent=lambda agent_id: _profile_accumulator(profiles, agent_id),
            artifact_kind_seen=artifact_kind_seen,
            artifact_missing_seen=artifact_missing_seen,
            evaluation_failed_seen=evaluation_failed_seen,
        )

    return [
        _finalize_profile(profile)
        for profile in sorted(
            profiles.values(),
            key=lambda item: (-item.task_count, item.agent_id),
        )
        if profile.task_count or profile.attempt_count
    ]
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


def _accumulate_task_event_insights(
    task: OrchestratorTask,
    attempts: list[OrchestratorTaskAttempt],
    events: list[OrchestratorRunEvent],
    participating_agents: set[str],
    *,
    profile_for_agent: Callable[[str], _AgentCapabilityAccumulator],
    artifact_kind_seen: set[tuple[str, UUID, str]],
    artifact_missing_seen: set[tuple[str, UUID, int | str]],
    evaluation_failed_seen: set[tuple[str, UUID, int | str]],
) -> None:
    for event in events:
        for insight in _event_attempt_insights(event):
            insight_agent = insight.agent_id or task.agent_id
            if insight_agent not in participating_agents:
                continue
            insight_profile = profile_for_agent(insight_agent)
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
    reason = safe_failure_reason_summary(reason)
    if not reason or reason in profile.recent_failure_reasons:
        return
    if len(profile.recent_failure_reasons) >= MAX_AGENT_FAILURE_REASONS:
        return
    profile.recent_failure_reasons.append(reason)


_RUNTIME_TRACE_MARKERS = (
    "OpenAI Codex",
    "Codex CLI exited",
    "workdir:",
    "approval:",
    "sandbox:",
    "System: AgentHub workspace rules",
    "Reading additional input from stdin",
    "/workspaces/",
)

_SENSITIVE_MARKERS = (
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "bearer ",
    "authorization:",
)


def safe_failure_reason_summary(reason: str | None) -> str | None:
    """Return a bounded failure signal safe for model context."""
    if not reason:
        return None
    clean = _single_line(reason, 240)
    lowered = clean.lower()
    if "insufficient balance" in lowered or "error code: 402" in lowered:
        return "upstream_error: insufficient_balance"
    if "runtime_idle_timeout" in lowered or "idle_timeout_seconds" in lowered:
        return "runtime_timeout: idle_timeout"
    if "runtime_hard_timeout" in lowered or "max_runtime_seconds" in lowered:
        return "runtime_timeout: hard_timeout"
    if "deterministic evaluation failed" in lowered:
        return "repair_attempt_after_evaluation_failed"
    if any(marker.lower() in lowered for marker in _RUNTIME_TRACE_MARKERS):
        code_match = re.search(r"\bcode\s+(-?\d+)\b", clean, flags=re.IGNORECASE)
        if code_match:
            return f"external_runtime_error: exit_code_{code_match.group(1)}"
        return "external_runtime_error"
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return "external_runtime_error"
    return _single_line(clean, 160)


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
