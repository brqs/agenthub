"""Shared types for AgentHub orchestrator execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from app.agents.base import BaseAgentAdapter

AdapterFactory = Callable[[str], BaseAgentAdapter | Awaitable[BaseAgentAdapter]]

DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS = 4000
DEFAULT_TASK_RESULT_ITEM_MAX_CHARS = 1200
DEFAULT_MAX_TASK_ATTEMPTS = 3
MAX_TASK_ATTEMPTS_LIMIT = 3


def _required_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid_task_plan: task.{key} must be a non-empty string")
    return value


def _optional_str(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid_task_plan: task.{key} must be a string")
    return value


def _task_type(raw: Mapping[str, Any]) -> str:
    value = raw.get("task_type", "implementation")
    if not isinstance(value, str):
        raise ValueError("invalid_task_plan: task.task_type must be a string")
    normalized = value.strip() or "implementation"
    if normalized not in {
        "implementation",
        "review",
        "repair",
        "conversation",
        "dialogue_turn",
    }:
        raise ValueError(
            "invalid_task_plan: task.task_type must be implementation, review, "
            "repair, conversation, or dialogue_turn"
        )
    return normalized


def _review_of(raw: Mapping[str, Any]) -> tuple[str, ...]:
    value = raw.get("review_of", [])
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if not isinstance(value, list):
        raise ValueError("invalid_task_plan: task.review_of must be a string or list")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("invalid_task_plan: task.review_of must contain strings")
    return tuple(item for item in value if item.strip())


def _depends_on(raw: Mapping[str, Any]) -> tuple[str, ...]:
    value = raw.get("depends_on", [])
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("invalid_task_plan: task.depends_on must be a list")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("invalid_task_plan: task.depends_on must contain strings")
    return tuple(value)


def _priority(raw: Mapping[str, Any]) -> int:
    value = raw.get("priority", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid_task_plan: task.priority must be an integer")
    return value


def _include_history(raw: Mapping[str, Any]) -> bool:
    value = raw.get("include_history", True)
    if not isinstance(value, bool):
        raise ValueError("invalid_task_plan: task.include_history must be a boolean")
    return value


class TaskState(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ARTIFACT_MISSING = "artifact_missing"
    EVALUATION_FAILED = "evaluation_failed"


@dataclass(frozen=True, slots=True)
class SubTask:
    task_id: str
    agent_id: str
    title: str
    instruction: str
    depends_on: tuple[str, ...] = ()
    priority: int = 0
    expected_output: str | None = None
    include_history: bool = True
    task_type: str = "implementation"
    review_of: tuple[str, ...] = ()
    handoff_reason: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SubTask:
        return cls(
            task_id=_required_str(raw, "task_id"),
            agent_id=_required_str(raw, "agent_id"),
            title=_required_str(raw, "title"),
            instruction=_required_str(raw, "instruction"),
            depends_on=_depends_on(raw),
            priority=_priority(raw),
            expected_output=_optional_str(raw, "expected_output"),
            include_history=_include_history(raw),
            task_type=_task_type(raw),
            review_of=_review_of(raw),
            handoff_reason=_optional_str(raw, "handoff_reason"),
        )


@dataclass(slots=True)
class TaskAttempt:
    attempt_index: int
    agent_id: str
    state: TaskState = TaskState.PENDING
    text_preview: str = ""
    tool_summaries: list[str] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    missing_artifact_paths: list[str] = field(default_factory=list)
    file_changes: dict[str, list[str]] = field(
        default_factory=lambda: {"created": [], "modified": [], "deleted": []}
    )
    conflict_paths: list[str] = field(default_factory=list)
    evaluation_results: list[Any] = field(default_factory=list)
    reflection: Any | None = None
    review_outcome: str | None = None
    error: str | None = None


@dataclass(slots=True)
class TaskResult:
    task_id: str
    title: str
    final_state: TaskState = TaskState.PENDING
    attempts: list[TaskAttempt] = field(default_factory=list)
    workspace_conflicts: list[dict[str, Any]] = field(default_factory=list)
    skipped_unavailable_agents: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OrchestratorRunContext:
    results: dict[str, TaskResult] = field(default_factory=dict)
    result_order: list[str] = field(default_factory=list)
    memory_run_id: UUID | None = None
    fulfillment_items: list[dict[str, Any]] = field(default_factory=list)
    workspace_conflict_event_keys: set[str] = field(default_factory=set)
    failed_runtime_agent_ids: set[str] = field(default_factory=set)
    runtime_agent_failure_reasons: dict[str, str] = field(default_factory=dict)
    runtime_agent_skip_reasons: dict[str, dict[str, str]] = field(default_factory=dict)

    def record(self, result: TaskResult) -> None:
        if result.task_id not in self.results:
            self.result_order.append(result.task_id)
        self.results[result.task_id] = result

    def mark_runtime_failed(self, agent_id: str, reason: str) -> None:
        clean_agent_id = agent_id.strip()
        if not clean_agent_id or clean_agent_id == "orchestrator":
            return
        self.failed_runtime_agent_ids.add(clean_agent_id)
        self.runtime_agent_failure_reasons[clean_agent_id] = reason

    def record_runtime_agent_skip(
        self,
        task_id: str,
        agent_id: str,
        reason: str,
    ) -> None:
        clean_agent_id = agent_id.strip()
        if not clean_agent_id or clean_agent_id == "orchestrator":
            return
        task_reasons = self.runtime_agent_skip_reasons.setdefault(task_id, {})
        task_reasons[clean_agent_id] = reason


class OrchestratorMemoryWriter(Protocol):
    """Optional persistence boundary for orchestrator run memory."""

    async def start_run(
        self,
        *,
        user_request: str,
        plan_source: str,
        tasks: list[SubTask],
    ) -> UUID: ...

    async def record_task_planned(
        self,
        *,
        run_id: UUID,
        task: SubTask,
    ) -> None: ...

    async def record_task_started(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        agent_id: str,
        attempt_index: int,
    ) -> None: ...

    async def record_task_result(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        result: TaskResult,
    ) -> None: ...

    async def record_event(
        self,
        *,
        run_id: UUID,
        event_type: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None: ...

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        final_summary: str,
    ) -> None: ...

    async def cancel_active_run(self) -> None: ...
