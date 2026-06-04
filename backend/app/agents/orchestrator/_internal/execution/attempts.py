"""Attempt configuration and message helpers for orchestrator execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.execution.summary import (
    task_result_context_message as _task_result_context_message,
)
from app.agents.orchestrator.types import (
    DEFAULT_MAX_TASK_ATTEMPTS,
    DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS,
    DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    MAX_TASK_ATTEMPTS_LIMIT,
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage


def task_messages(
    task: SubTask,
    messages: list[ChatMessage],
    run_context: OrchestratorRunContext,
    config: Mapping[str, Any],
    *,
    previous_attempt: TaskAttempt | None = None,
) -> list[ChatMessage]:
    task_message = ChatMessage(role="user", content=task.instruction)
    context_message = _task_result_context_message(
        run_context,
        task,
        context_max_chars=task_result_context_max_chars(config),
        item_max_chars=task_result_item_max_chars(config),
        previous_attempt=previous_attempt,
    )
    base_messages = [*messages] if task.include_history else []
    if context_message is not None:
        base_messages.append(context_message)
    base_messages.append(task_message)
    return base_messages


def task_fallback_agent_ids(config: Mapping[str, Any]) -> list[str]:
    value = config.get("task_fallback_agent_ids")
    if not isinstance(value, list):
        return []
    allowed_agent_ids = allowed_fallback_agent_ids(config)
    return dedupe_strings(
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
        and item.strip() != "orchestrator"
        and (not allowed_agent_ids or item.strip() in allowed_agent_ids)
    )


def allowed_fallback_agent_ids(config: Mapping[str, Any]) -> set[str]:
    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        ids = {
            agent_id
            for item in available_agents
            if isinstance(item, Mapping)
            and isinstance((agent_id := item.get("agent_id", item.get("id"))), str)
            and agent_id.strip()
            and agent_id.strip() != "orchestrator"
        }
        if ids:
            return {agent_id.strip() for agent_id in ids}
    for key in ("managed_agent_ids", "default_sub_agents"):
        value = config.get(key)
        if isinstance(value, list):
            ids = {
                item.strip()
                for item in value
                if isinstance(item, str)
                and item.strip()
                and item.strip() != "orchestrator"
            }
            if ids:
                return ids
    return set()


def max_task_attempts(config: Mapping[str, Any]) -> int:
    value = config.get("max_task_attempts", DEFAULT_MAX_TASK_ATTEMPTS)
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_MAX_TASK_ATTEMPTS
    return int(min(max(value, 1), MAX_TASK_ATTEMPTS_LIMIT))


def parallel_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_parallel_enabled") is True


def parallel_max_concurrency(config: Mapping[str, Any]) -> int:
    value = config.get("orchestrator_parallel_max_concurrency", 3)
    if isinstance(value, bool) or not isinstance(value, int):
        return 3
    return max(1, min(value, 10))


def changes_for_attempt_artifacts(
    changes: dict[str, list[str]],
    artifact_paths: list[str],
) -> dict[str, list[str]]:
    if not artifact_paths:
        return changes
    allowed = set(artifact_paths)
    return {
        key: [path for path in paths if path in allowed]
        for key, paths in changes.items()
    }


def task_result_context_max_chars(config: Mapping[str, Any]) -> int:
    return positive_int_config(
        config,
        "task_result_context_max_chars",
        DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS,
    )


def task_result_item_max_chars(config: Mapping[str, Any]) -> int:
    return positive_int_config(
        config,
        "task_result_item_max_chars",
        DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    )


def positive_int_config(
    config: Mapping[str, Any],
    key: str,
    default: int,
) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return int(value)


def agent_for_attempt(
    task: SubTask,
    fallback_agents: list[str],
    attempted_agents: set[str],
) -> str | None:
    if not attempted_agents:
        return task.agent_id
    for agent_id in fallback_agents:
        if agent_id not in attempted_agents:
            return agent_id
    return None


def can_retry_task(
    result: TaskResult,
    fallback_agents: list[str],
    max_attempts: int,
) -> bool:
    if not fallback_agents or len(result.attempts) >= max_attempts:
        return False
    return result.final_state in {
        TaskState.FAILED,
        TaskState.ARTIFACT_MISSING,
        TaskState.EVALUATION_FAILED,
    }


def attempt_call_id_prefix(
    task_id: str,
    attempt_index: int,
    *,
    call_id_prefix: str | None = None,
) -> str:
    base = call_id_prefix or task_id
    if attempt_index == 1:
        return base
    return f"{base}.attempt-{attempt_index}"


def dedupe_strings(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output
