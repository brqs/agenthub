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
DEFAULT_MAX_TASK_ATTEMPTS = 1
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
    error: str | None = None


@dataclass(slots=True)
class TaskResult:
    task_id: str
    title: str
    final_state: TaskState = TaskState.PENDING
    attempts: list[TaskAttempt] = field(default_factory=list)


@dataclass(slots=True)
class OrchestratorRunContext:
    results: dict[str, TaskResult] = field(default_factory=dict)
    result_order: list[str] = field(default_factory=list)
    memory_run_id: UUID | None = None

    def record(self, result: TaskResult) -> None:
        if result.task_id not in self.results:
            self.result_order.append(result.task_id)
        self.results[result.task_id] = result


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
