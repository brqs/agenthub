"""User-scoped Agent Capability Profile v2 aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from math import exp, log
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestrator_memory import (
    OrchestratorRun,
    OrchestratorTask,
    OrchestratorTaskAttempt,
)
from app.services._orchestrator_memory.capability_v1 import (
    _accumulate_artifact_kinds,
    _accumulate_failure_event,
    _accumulate_failure_reason,
    _accumulate_task_event_insights,
    _attempt_failure_reason,
    _finalize_profile,
)
from app.services._orchestrator_memory.queries import (
    _attempts_by_task,
    _recent_user_terminal_runs,
    _task_result_events_by_task,
    _tasks_for_runs,
)
from app.services._orchestrator_memory.types import (
    DEFAULT_AGENT_CAPABILITY_PROFILE_V2_HALF_LIFE_DAYS,
    DEFAULT_AGENT_CAPABILITY_PROFILE_V2_LIMIT,
    DEFAULT_AGENT_CAPABILITY_PROFILE_V2_RECENT_RUNS,
    FAILED_TASK_STATES,
    MAX_AGENT_CAPABILITY_PROFILE_RECENT_RUNS,
    MAX_AGENT_FAILURE_REASONS,
    TIMEOUT_MARKERS,
    AgentCapabilityProfileV2,
    AgentCapabilityProfileV2Item,
    _AgentCapabilityV2Accumulator,
)
from app.services.artifacts.metadata import classify_artifact


async def build_agent_capability_profile_v2(
    db: AsyncSession,
    user_id: UUID,
    *,
    conversation_id: UUID | None = None,
    recent_runs: int = DEFAULT_AGENT_CAPABILITY_PROFILE_V2_RECENT_RUNS,
    half_life_days: float = DEFAULT_AGENT_CAPABILITY_PROFILE_V2_HALF_LIFE_DAYS,
    limit: int = DEFAULT_AGENT_CAPABILITY_PROFILE_V2_LIMIT,
) -> AgentCapabilityProfileV2:
    """Aggregate user-scoped Orchestrator outcomes across owned conversations."""
    recent_runs = max(1, min(recent_runs, MAX_AGENT_CAPABILITY_PROFILE_RECENT_RUNS))
    limit = max(1, min(limit, 100))
    half_life_days = max(1.0, min(float(half_life_days), 365.0))
    generated_at = datetime.now(UTC)
    runs = await _recent_user_terminal_runs(db, user_id, limit=recent_runs)
    source_conversation_count = len({run.conversation_id for run in runs})
    from app.services._orchestrator_memory.preferences import (
        _build_user_preference_memory,
    )

    preferences = await _build_user_preference_memory(db, runs)
    if not runs:
        return AgentCapabilityProfileV2(
            items=[],
            preferences=preferences,
            scope="user",
            source_conversation_count=0,
            runs_considered=0,
            generated_at=generated_at,
        )

    run_by_id = {run.id: run for run in runs}
    run_ids = list(run_by_id)
    tasks = await _tasks_for_runs(db, run_ids)
    attempts_by_task = await _attempts_by_task(db, [task.id for task in tasks])
    events_by_task = await _task_result_events_by_task(db, run_ids)

    profiles: dict[str, _AgentCapabilityV2Accumulator] = {}
    artifact_kind_seen: set[tuple[str, UUID, str]] = set()
    artifact_missing_seen: set[tuple[str, UUID, int | str]] = set()
    evaluation_failed_seen: set[tuple[str, UUID, int | str]] = set()

    for task in tasks:
        run = run_by_id.get(task.run_id)
        if run is None:
            continue
        weight = _run_decay_weight(
            run,
            now=generated_at,
            half_life_days=half_life_days,
            current_conversation_id=conversation_id,
        )
        attempts = attempts_by_task.get(task.id, [])
        participating_agents = _accumulate_task_participation_v2(
            profiles,
            task,
            run,
            attempts,
            weight=weight,
            artifact_kind_seen=artifact_kind_seen,
            artifact_missing_seen=artifact_missing_seen,
            evaluation_failed_seen=evaluation_failed_seen,
        )

        _accumulate_task_event_insights(
            task,
            attempts,
            events_by_task.get((task.run_id, task.task_id), []),
            participating_agents,
            profile_for_agent=lambda agent_id: _profile_v2_accumulator(
                profiles, agent_id
            ),
            artifact_kind_seen=artifact_kind_seen,
            artifact_missing_seen=artifact_missing_seen,
            evaluation_failed_seen=evaluation_failed_seen,
        )

    items = [
        _finalize_profile_v2(profile)
        for profile in profiles.values()
        if profile.task_count or profile.attempt_count
    ]
    items.sort(key=lambda item: (-item.score, -item.task_count, item.agent_id))
    return AgentCapabilityProfileV2(
        items=items[:limit],
        preferences=preferences,
        scope="user",
        source_conversation_count=source_conversation_count,
        runs_considered=len(runs),
        generated_at=generated_at,
    )
def _profile_v2_accumulator(
    profiles: dict[str, _AgentCapabilityV2Accumulator],
    agent_id: str,
) -> _AgentCapabilityV2Accumulator:
    profile = profiles.get(agent_id)
    if profile is None:
        profile = _AgentCapabilityV2Accumulator(agent_id=agent_id)
        profiles[agent_id] = profile
    return profile


def _accumulate_task_participation_v2(
    profiles: dict[str, _AgentCapabilityV2Accumulator],
    task: OrchestratorTask,
    run: OrchestratorRun,
    attempts: list[OrchestratorTaskAttempt],
    *,
    weight: float,
    artifact_kind_seen: set[tuple[str, UUID, str]],
    artifact_missing_seen: set[tuple[str, UUID, int | str]],
    evaluation_failed_seen: set[tuple[str, UUID, int | str]],
) -> set[str]:
    attempts_by_agent: dict[str, list[OrchestratorTaskAttempt]] = {}
    for attempt in attempts:
        attempts_by_agent.setdefault(attempt.agent_id, []).append(attempt)

    if not attempts_by_agent:
        return _accumulate_legacy_task_v2(profiles, task, run, weight=weight)

    participating_agents: set[str] = set()
    for agent_id, agent_attempts in attempts_by_agent.items():
        if not any(attempt.state not in {"pending", "skipped"} for attempt in agent_attempts):
            continue
        participating_agents.add(agent_id)
        profile = _profile_v2_accumulator(profiles, agent_id)
        _accumulate_task_base_v2(profile, task, run, weight=weight)
        profile.attempt_count += len(agent_attempts)
        final_attempt = agent_attempts[-1]
        if final_attempt.state == "succeeded":
            profile.success_count += 1
            profile.weighted_success_score += weight
            if task.task_type == "repair":
                profile.repair_success_count += 1
        elif final_attempt.state in FAILED_TASK_STATES:
            profile.failure_count += 1
            profile.weighted_failure_score += weight

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

        if any(_attempt_timed_out(attempt) for attempt in agent_attempts):
            profile.timeout_count += 1
            _accumulate_failure_reason(profile, "timeout")

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


def _accumulate_legacy_task_v2(
    profiles: dict[str, _AgentCapabilityV2Accumulator],
    task: OrchestratorTask,
    run: OrchestratorRun,
    *,
    weight: float,
) -> set[str]:
    if task.final_state in {"pending", "skipped"}:
        return set()
    profile = _profile_v2_accumulator(profiles, task.agent_id)
    _accumulate_task_base_v2(profile, task, run, weight=weight)
    if task.final_state == "succeeded":
        profile.success_count += 1
        profile.weighted_success_score += weight
        if task.task_type == "repair":
            profile.repair_success_count += 1
    elif task.final_state in FAILED_TASK_STATES:
        profile.failure_count += 1
        profile.weighted_failure_score += weight
    if task.final_state == "artifact_missing":
        profile.artifact_missing_count += 1
    if task.final_state == "evaluation_failed":
        profile.evaluation_failed_count += 1
    _accumulate_failure_reason(
        profile,
        task.final_state if task.final_state in FAILED_TASK_STATES else None,
    )
    return {task.agent_id}


def _accumulate_task_base_v2(
    profile: _AgentCapabilityV2Accumulator,
    task: OrchestratorTask,
    run: OrchestratorRun,
    *,
    weight: float,
) -> None:
    profile.run_ids.add(task.run_id)
    profile.conversation_ids.add(run.conversation_id)
    profile.task_count += 1
    profile.weighted_task_count += weight
    profile.task_types.update([task.task_type or "implementation"])
    for taxonomy in _task_taxonomy(task):
        profile.task_taxonomy.update([taxonomy])


def _run_decay_weight(
    run: OrchestratorRun,
    *,
    now: datetime,
    half_life_days: float,
    current_conversation_id: UUID | None,
) -> float:
    created_at = run.completed_at or run.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    age_days = max((now - created_at).total_seconds() / 86400.0, 0.0)
    weight = exp(-log(2) * age_days / half_life_days)
    if current_conversation_id is not None and run.conversation_id == current_conversation_id:
        weight *= 1.25
    return weight


def _task_taxonomy(task: OrchestratorTask) -> set[str]:
    text = " ".join(
        part
        for part in (
            task.task_type,
            task.title,
            task.instruction,
            task.expected_output or "",
        )
        if part
    ).lower()
    taxonomy: set[str] = set()
    if task.task_type in {"review", "repair"}:
        taxonomy.add(task.task_type)
    keyword_map = {
        "document": ("doc", "markdown", ".md", "report", "说明", "文档", "报告"),
        "frontend": ("frontend", "index.html", "css", "app.js", "移动端", "网页", "前端"),
        "backend": ("backend", "api", "pytest", "fastapi", "后端", "接口"),
        "deployment": ("deploy", "preview", "port", "8082", "公网", "部署", "预览"),
        "workflow": ("workflow", "工作流", "yaml"),
        "presentation": ("ppt", "slide", "presentation", "演示", "幻灯"),
        "data": ("csv", "json", "dataset", "数据"),
    }
    for name, markers in keyword_map.items():
        if any(marker in text for marker in markers):
            taxonomy.add(name)
    return taxonomy or {"general"}


def _attempt_timed_out(attempt: OrchestratorTaskAttempt) -> bool:
    text = f"{attempt.state} {attempt.error or ''}".lower()
    return any(marker in text for marker in TIMEOUT_MARKERS)


def _finalize_profile_v2(
    profile: _AgentCapabilityV2Accumulator,
) -> AgentCapabilityProfileV2Item:
    base = _finalize_profile(profile)
    weighted_total = profile.weighted_success_score + profile.weighted_failure_score
    success_rate = (
        round(profile.weighted_success_score / weighted_total, 3)
        if weighted_total
        else 0.0
    )
    score, score_reasons = _profile_v2_score(profile, success_rate)
    return AgentCapabilityProfileV2Item(
        agent_id=base.agent_id,
        runs_considered=base.runs_considered,
        task_count=base.task_count,
        success_count=base.success_count,
        failure_count=base.failure_count,
        artifact_missing_count=base.artifact_missing_count,
        evaluation_failed_count=base.evaluation_failed_count,
        avg_attempts=base.avg_attempts,
        artifact_kinds=base.artifact_kinds,
        review_outcomes=base.review_outcomes,
        repair_success_count=base.repair_success_count,
        recent_failure_reasons=base.recent_failure_reasons,
        confidence=base.confidence,
        scope="user",
        conversation_count=len(profile.conversation_ids),
        weighted_task_count=round(profile.weighted_task_count, 3),
        weighted_success_score=round(profile.weighted_success_score, 3),
        weighted_failure_score=round(profile.weighted_failure_score, 3),
        success_rate=success_rate,
        timeout_count=profile.timeout_count,
        task_types=dict(profile.task_types.most_common()),
        task_taxonomy=dict(profile.task_taxonomy.most_common()),
        score=score,
        score_reasons=score_reasons,
    )


def _profile_v2_score(
    profile: _AgentCapabilityV2Accumulator,
    success_rate: float,
) -> tuple[float, list[str]]:
    score = (
        profile.weighted_success_score * 2.0
        + profile.repair_success_count * 0.8
        + success_rate
        - profile.weighted_failure_score * 1.5
        - profile.evaluation_failed_count * 0.6
        - profile.artifact_missing_count * 0.5
        - profile.timeout_count * 0.8
    )
    if profile.task_count < 2:
        score *= 0.45
    elif profile.task_count < 5:
        score *= 0.75
    reasons: list[str] = []
    if profile.weighted_success_score:
        reasons.append(f"weighted_success={profile.weighted_success_score:.2f}")
    if profile.weighted_failure_score:
        reasons.append(f"weighted_failure={profile.weighted_failure_score:.2f}")
    if profile.repair_success_count:
        reasons.append(f"repair_success={profile.repair_success_count}")
    if profile.evaluation_failed_count:
        reasons.append(f"evaluation_failed={profile.evaluation_failed_count}")
    if profile.artifact_missing_count:
        reasons.append(f"artifact_missing={profile.artifact_missing_count}")
    if profile.timeout_count:
        reasons.append(f"timeout={profile.timeout_count}")
    if profile.task_count < 2:
        reasons.append("low_sample_confidence")
    if profile.task_taxonomy:
        top_taxonomy = profile.task_taxonomy.most_common(1)[0]
        reasons.append(f"top_task_taxonomy={top_taxonomy[0]}")
    return round(score, 3), reasons[:MAX_AGENT_FAILURE_REASONS]
