"""Attempt configuration and message helpers for orchestrator execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.orchestrator._internal.execution.summary import (
    task_result_context_message as _task_result_context_message,
)
from app.agents.orchestrator.availability import (
    runnable_agent_ids,
    runtime_cooldown_status,
    scoped_runnable_agent_ids,
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


@dataclass(frozen=True, slots=True)
class AttemptAgentSelection:
    agent_id: str | None
    skipped_agent_ids: tuple[str, ...] = ()


def task_messages(
    task: SubTask,
    messages: list[ChatMessage],
    run_context: OrchestratorRunContext,
    config: Mapping[str, Any],
    *,
    workspace_path: Path | None = None,
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
        if previous_attempt is None:
            base_messages.append(context_message)
    inventory_message = _workspace_inventory_message(task, workspace_path)
    if inventory_message is not None:
        base_messages.append(inventory_message)
    if context_message is not None and previous_attempt is not None:
        base_messages.append(context_message)
    base_messages.append(task_message)
    return base_messages


def _workspace_inventory_message(
    task: SubTask,
    workspace_path: Path | None,
) -> ChatMessage | None:
    if workspace_path is None:
        return None
    root_entries = _root_entries(workspace_path)
    expected_paths = _expected_paths(task)
    existing_expected = [
        path for path in expected_paths if (workspace_path / path).is_file()
    ]
    if not root_entries and not expected_paths:
        return None
    lines = ["Workspace inventory for this task:"]
    if root_entries:
        lines.append(f"Current root entries: {', '.join(root_entries[:40])}")
    if existing_expected:
        lines.append(
            f"Existing expected artifacts: {', '.join(existing_expected[:20])}"
        )
    if expected_paths:
        lines.append(
            "If you edit an existing expected artifact, read or inspect that file "
            "first before writing to it."
        )
    return ChatMessage(role="system", content="\n".join(lines))


def _root_entries(workspace_path: Path) -> list[str]:
    try:
        return sorted(
            item.name
            for item in workspace_path.iterdir()
            if item.name and not item.name.startswith(".")
        )
    except OSError:
        return []


def _expected_paths(task: SubTask) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for line in (task.expected_output or "").splitlines():
        path = line.strip().strip("-* ")
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def task_fallback_agent_ids(config: Mapping[str, Any]) -> list[str]:
    if config.get("task_auto_fallback_enabled") is False:
        return []
    ordered_runnable_ids = _ordered_runnable_agent_ids(config)
    strict_scope = scoped_runnable_agent_ids(config)
    strict_allowed = set(strict_scope) if strict_scope is not None else None
    runnable_allowed = set(ordered_runnable_ids) if ordered_runnable_ids else None

    def permitted(agent_id: str) -> bool:
        if agent_id == "orchestrator":
            return False
        if strict_allowed is not None:
            return agent_id in strict_allowed
        if runnable_allowed is not None:
            return agent_id in runnable_allowed
        return True

    candidates: list[str] = []
    value = config.get("task_fallback_agent_ids")
    if isinstance(value, list):
        candidates.extend(
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip() and permitted(item.strip())
        )
    candidates.extend(agent_id for agent_id in ordered_runnable_ids if permitted(agent_id))
    return dedupe_strings(candidates)


def allowed_fallback_agent_ids(config: Mapping[str, Any]) -> set[str]:
    scoped_ids = scoped_runnable_agent_ids(config)
    if scoped_ids is not None:
        return set(scoped_ids)

    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        ids = set(runnable_agent_ids(available_agents))
        if ids:
            return ids
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


def _ordered_runnable_agent_ids(config: Mapping[str, Any]) -> list[str]:
    scoped_ids = scoped_runnable_agent_ids(config)
    if scoped_ids is not None:
        return list(scoped_ids)

    agent_ids: list[str] = []
    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        agent_ids.extend(runnable_agent_ids(available_agents))

    for key in ("managed_agent_ids", "default_sub_agents"):
        value = config.get(key)
        if isinstance(value, list):
            agent_ids.extend(
                item.strip()
                for item in value
                if isinstance(item, str)
                and item.strip()
                and item.strip() != "orchestrator"
            )

    sub_adapters = config.get("sub_adapters")
    if isinstance(sub_adapters, Mapping):
        agent_ids.extend(
            agent_id.strip()
            for agent_id in sub_adapters
            if isinstance(agent_id, str)
            and agent_id.strip()
            and agent_id.strip() != "orchestrator"
        )
    return dedupe_strings(agent_ids)


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
    considered_agents: set[str],
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    *,
    excluded_agent_ids: set[str] | None = None,
) -> AttemptAgentSelection:
    skipped_agent_ids: list[str] = []
    candidate_ids = dedupe_strings([task.agent_id, *fallback_agents])
    excluded_agent_ids = excluded_agent_ids or set()
    for agent_id in candidate_ids:
        if agent_id in considered_agents:
            continue
        if agent_id in excluded_agent_ids:
            continue
        if not agent_permitted_for_attempt(config, run_context, agent_id):
            skipped_agent_ids.append(agent_id)
            continue
        return AttemptAgentSelection(agent_id=agent_id, skipped_agent_ids=tuple(skipped_agent_ids))
    for agent_id in candidate_ids:
        if agent_id in considered_agents:
            continue
        if agent_id in excluded_agent_ids:
            continue
        if not agent_permitted_for_attempt(
            config,
            run_context,
            agent_id,
            ignore_global_cooldown=True,
        ):
            continue
        return AttemptAgentSelection(agent_id=agent_id, skipped_agent_ids=tuple(skipped_agent_ids))
    return AttemptAgentSelection(agent_id=None, skipped_agent_ids=tuple(skipped_agent_ids))


def agent_permitted_for_attempt(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    agent_id: str,
    *,
    ignore_global_cooldown: bool = False,
) -> bool:
    if agent_id == "orchestrator" or agent_id in run_context.failed_runtime_agent_ids:
        return False
    if not ignore_global_cooldown and runtime_cooldown_status(agent_id)[0] == "cooldown":
        return False

    scoped_ids = scoped_runnable_agent_ids(config)
    if scoped_ids is not None:
        return agent_id in set(scoped_ids)

    runnable_ids = _ordered_runnable_agent_ids(config)
    if runnable_ids:
        return agent_id in set(runnable_ids)
    return True


def preferred_agent_for_task(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    task: SubTask,
) -> str | None:
    fallback_agents = task_fallback_agent_ids(config)
    for agent_id in dedupe_strings([task.agent_id, *fallback_agents]):
        if agent_permitted_for_attempt(config, run_context, agent_id):
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
