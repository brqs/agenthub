"""Shared types and constants for Orchestrator structured memory."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS = 3
DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS = 24000
DEFAULT_AGENT_CAPABILITY_PROFILE_RECENT_RUNS = 20
DEFAULT_AGENT_CAPABILITY_PROFILE_V2_RECENT_RUNS = 60
DEFAULT_AGENT_CAPABILITY_PROFILE_V2_HALF_LIFE_DAYS = 30.0
DEFAULT_AGENT_CAPABILITY_PROFILE_V2_LIMIT = 10
MAX_AGENT_CAPABILITY_PROFILE_RECENT_RUNS = 100
MAX_AGENT_FAILURE_REASONS = 5
MAX_USER_PREFERENCE_ITEMS = 8
MAX_TEXT_PREVIEW_CHARS = 4000
MAX_EVENT_PAYLOAD_TEXT_CHARS = 2000
TERMINAL_RUN_STATUSES = {"done", "error", "cancelled", "interrupted"}
FAILED_TASK_STATES = {"failed", "artifact_missing", "evaluation_failed"}
TIMEOUT_MARKERS = ("timeout", "timed out", "idle timeout", "request timeout")


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


@dataclass(slots=True)
class AgentCapabilityProfileV2Item(AgentCapabilityProfileItem):
    scope: str = "user"
    conversation_count: int = 0
    weighted_task_count: float = 0.0
    weighted_success_score: float = 0.0
    weighted_failure_score: float = 0.0
    success_rate: float = 0.0
    timeout_count: int = 0
    task_types: dict[str, int] = field(default_factory=dict)
    task_taxonomy: dict[str, int] = field(default_factory=dict)
    score: float = 0.0
    score_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UserPreferenceMemory:
    runs_considered: int = 0
    source_conversation_count: int = 0
    domains: dict[str, int] = field(default_factory=dict)
    artifact_preferences: dict[str, int] = field(default_factory=dict)
    deployment_preferences: dict[str, int] = field(default_factory=dict)
    language_style_hints: dict[str, int] = field(default_factory=dict)
    summary: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentCapabilityProfileV2:
    items: list[AgentCapabilityProfileV2Item]
    preferences: UserPreferenceMemory
    scope: str
    source_conversation_count: int
    runs_considered: int
    generated_at: datetime


@dataclass(slots=True)
class _AgentCapabilityV2Accumulator(_AgentCapabilityAccumulator):
    conversation_ids: set[UUID] = field(default_factory=set)
    weighted_task_count: float = 0.0
    weighted_success_score: float = 0.0
    weighted_failure_score: float = 0.0
    timeout_count: int = 0
    task_types: Counter[str] = field(default_factory=Counter)
    task_taxonomy: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True, slots=True)
class _EventAttemptInsight:
    agent_id: str | None
    attempt_index: int | None
    artifact_kinds: set[str]
    artifact_missing: bool
    evaluation_failed: bool
    failure_reasons: list[str]
