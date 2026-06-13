"""ReAct task-graph mutation and validation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.agents.orchestrator._internal.react.types import ReactDecision, ReactDecisionError
from app.agents.orchestrator.availability import (
    runnable_agent_ids,
    scoped_runnable_agent_ids,
)
from app.agents.orchestrator.types import SubTask, TaskState

AgentIdList = Callable[[object], list[str]]


def _apply_react_decision(
    decision: ReactDecision,
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
    config: Mapping[str, Any],
    agent_id_list: AgentIdList,
) -> tuple[list[SubTask], dict[str, TaskState], str | None]:
    draft_tasks = list(tasks)
    draft_states = dict(task_states)
    finish_reason: str | None = None

    for action in decision.actions:
        action_type = action.get("type")
        if action_type == "add_task":
            _react_add_task(action, draft_tasks, draft_states, config, agent_id_list)
        elif action_type == "update_task":
            _react_update_task(action, draft_tasks, draft_states, config, agent_id_list)
        elif action_type == "skip_task":
            _react_skip_task(action, draft_tasks, draft_states)
        elif action_type == "finish":
            reason = action.get("reason")
            finish_reason = reason if isinstance(reason, str) and reason else "finished"
        else:
            raise ReactDecisionError(f"unknown react action {action_type!r}")

    _validate_task_graph(draft_tasks, _allowed_agent_id_set(config, agent_id_list))
    return sorted(draft_tasks, key=lambda task: task.priority), draft_states, finish_reason

def _react_add_task(
    action: Mapping[str, Any],
    tasks: list[SubTask],
    task_states: dict[str, TaskState],
    config: Mapping[str, Any],
    agent_id_list: AgentIdList,
) -> None:
    raw_task = action.get("task")
    if not isinstance(raw_task, Mapping):
        raise ReactDecisionError("add_task requires task object")
    task = SubTask.from_mapping(raw_task)
    if task.task_id in task_states:
        raise ReactDecisionError(f"duplicate task_id {task.task_id!r}")
    if task.agent_id not in _allowed_agent_id_set(config, agent_id_list):
        raise ReactDecisionError(f"unknown agent_id {task.agent_id!r}")
    tasks.append(task)
    task_states[task.task_id] = TaskState.PENDING

def _react_update_task(
    action: Mapping[str, Any],
    tasks: list[SubTask],
    task_states: dict[str, TaskState],
    config: Mapping[str, Any],
    agent_id_list: AgentIdList,
) -> None:
    task_id = action.get("task_id")
    patch = action.get("patch")
    if not isinstance(task_id, str) or not task_id:
        raise ReactDecisionError("update_task requires task_id")
    if not isinstance(patch, Mapping):
        raise ReactDecisionError("update_task requires patch object")
    state = task_states.get(task_id)
    if state is None:
        raise ReactDecisionError(f"unknown task_id {task_id!r}")
    if state != TaskState.PENDING:
        raise ReactDecisionError(f"cannot update completed task {task_id!r}")
    for index, task in enumerate(tasks):
        if task.task_id != task_id:
            continue
        raw = {
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "title": task.title,
            "instruction": task.instruction,
            "depends_on": list(task.depends_on),
            "priority": task.priority,
            "expected_output": task.expected_output,
            "include_history": task.include_history,
            "task_type": task.task_type,
        }
        for key in (
            "agent_id",
            "title",
            "instruction",
            "depends_on",
            "priority",
            "expected_output",
            "include_history",
            "task_type",
        ):
            if key in patch:
                raw[key] = patch[key]
        updated = SubTask.from_mapping(raw)
        if updated.agent_id not in _allowed_agent_id_set(config, agent_id_list):
            raise ReactDecisionError(f"unknown agent_id {updated.agent_id!r}")
        tasks[index] = updated
        return
    raise ReactDecisionError(f"unknown task_id {task_id!r}")

def _react_skip_task(
    action: Mapping[str, Any],
    tasks: list[SubTask],
    task_states: dict[str, TaskState],
) -> None:
    task_id = action.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ReactDecisionError("skip_task requires task_id")
    state = task_states.get(task_id)
    if state is None:
        raise ReactDecisionError(f"unknown task_id {task_id!r}")
    if state != TaskState.PENDING:
        raise ReactDecisionError(f"cannot skip completed task {task_id!r}")
    task_states[task_id] = TaskState.SKIPPED

def _validate_task_graph(tasks: list[SubTask], allowed_agent_ids: set[str]) -> None:
    task_ids = {task.task_id for task in tasks}
    for task in tasks:
        if task.agent_id not in allowed_agent_ids:
            raise ReactDecisionError(f"unknown agent_id {task.agent_id!r}")
        for dependency in task.depends_on:
            if dependency not in task_ids:
                raise ReactDecisionError(f"unknown depends_on task_id {dependency!r}")

def _allowed_agent_ids(config: Mapping[str, Any], agent_id_list: AgentIdList) -> list[str]:
    scoped_ids = scoped_runnable_agent_ids(config)
    if scoped_ids is not None:
        return scoped_ids
    ids = runnable_agent_ids(config.get("available_agents"))
    if ids:
        return ids
    return agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))

def _allowed_agent_id_set(config: Mapping[str, Any], agent_id_list: AgentIdList) -> set[str]:
    return set(_allowed_agent_ids(config, agent_id_list))

def _agent_ids_from_available_agents(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        raw_id = item.get("agent_id", item.get("id"))
        if not isinstance(raw_id, str):
            continue
        agent_id = raw_id.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        ids.append(agent_id)
    return ids
