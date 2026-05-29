"""ReAct dynamic task graph execution for the orchestrator."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator_types import (
    DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

DEFAULT_REACT_DECISION_MAX_TOKENS = 1024
MAX_REACT_DECISION_MAX_TOKENS = 4096

RunTask = Callable[
    [
        Mapping[str, Any],
        SubTask,
        list[ChatMessage],
        int,
        OrchestratorRunContext,
        Path | None,
        list[ToolSpec] | None,
    ],
    AsyncIterator[tuple[StreamChunk, int]],
]
TextBlockWithNext = Callable[[int, str], Iterable[tuple[StreamChunk, int]]]
SummaryText = Callable[[list[SubTask], Mapping[str, TaskState], OrchestratorRunContext], str]
FormatTaskResultContext = Callable[[str, TaskResult, int], str]
LatestUserRequest = Callable[[list[ChatMessage]], str]
PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]
AgentIdList = Callable[[object], list[str]]
ErrorReason = Callable[[StreamChunk], str]


class ReactDecisionError(ValueError):
    """Raised when ReAct replanner output cannot be safely applied."""


@dataclass(frozen=True, slots=True)
class ReactDecision:
    actions: list[Mapping[str, Any]]
    summary: str = ""


async def run_react_loop(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    *,
    run_task: RunTask,
    text_block_with_next: TextBlockWithNext,
    summary_text: SummaryText,
    format_task_result_context: FormatTaskResultContext,
    latest_user_request: LatestUserRequest,
    positive_int_config: PositiveIntConfig,
    agent_id_list: AgentIdList,
    error_reason: ErrorReason,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    task_graph = list(tasks)
    task_states = {task.task_id: TaskState.PENDING for task in task_graph}
    run_context = OrchestratorRunContext()
    max_iterations = _max_iterations(config, positive_int_config)
    finish_reason: str | None = None

    for iteration in range(1, max_iterations + 1):
        task = _next_runnable_task(task_graph, task_states)
        observation = "No runnable task is currently available."

        if task is not None:
            async for chunk, updated_block_index in run_task(
                config,
                task,
                messages,
                next_block_index,
                run_context,
                workspace_path,
                tool_specs,
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
            task_states[task.task_id] = run_context.results[task.task_id].final_state
            observation = _react_observation_text(
                task,
                run_context.results[task.task_id],
                format_task_result_context,
            )
        elif _all_tasks_terminal(task_states):
            observation = "All known tasks are terminal."

        if iteration >= max_iterations:
            finish_reason = f"max_iterations reached ({max_iterations})"
            if react_trace_visible(config):
                for chunk, updated_block_index in text_block_with_next(
                    next_block_index,
                    _react_trace_text(iteration, observation, finish_reason),
                ):
                    next_block_index = updated_block_index
                    yield chunk, updated_block_index
            break

        try:
            decision = await _react_decision(
                config,
                messages,
                task_graph,
                task_states,
                run_context,
                iteration,
                max_iterations,
                observation,
                format_task_result_context=format_task_result_context,
                latest_user_request=latest_user_request,
                positive_int_config=positive_int_config,
                agent_id_list=agent_id_list,
                error_reason=error_reason,
            )
            task_graph, task_states, finish_reason = _apply_react_decision(
                decision,
                task_graph,
                task_states,
                config,
                agent_id_list,
            )
        except ReactDecisionError as exc:
            finish_reason = f"ReAct replanner stopped: {exc}"
            if react_trace_visible(config):
                for chunk, updated_block_index in text_block_with_next(
                    next_block_index,
                    _react_trace_text(iteration, observation, finish_reason),
                ):
                    next_block_index = updated_block_index
                    yield chunk, updated_block_index
            break

        if react_trace_visible(config):
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                _react_trace_text(
                    iteration,
                    observation,
                    _react_action_summary(decision),
                ),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index

        if finish_reason is not None:
            break
        if not decision.actions and _all_tasks_terminal(task_states):
            finish_reason = "all tasks are terminal"
            break

    for chunk, updated_block_index in text_block_with_next(
        next_block_index,
        summary_text(task_graph, task_states, run_context),
    ):
        yield chunk, updated_block_index


def react_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("react_enabled") is True


def _next_runnable_task(
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
) -> SubTask | None:
    for task in sorted(tasks, key=lambda item: item.priority):
        if task_states.get(task.task_id) != TaskState.PENDING:
            continue
        if _dependencies_satisfied(task, task_states):
            return task
    return None


def _dependencies_satisfied(
    task: SubTask,
    task_states: Mapping[str, TaskState],
) -> bool:
    return all(task_states.get(dependency) == TaskState.SUCCEEDED for dependency in task.depends_on)


def _all_tasks_terminal(task_states: Mapping[str, TaskState]) -> bool:
    return all(state != TaskState.PENDING for state in task_states.values())


def react_trace_visible(config: Mapping[str, Any]) -> bool:
    return config.get("react_trace_visible", True) is not False


def _max_iterations(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    return positive_int_config(config, "max_iterations", 10)


def _react_decision_max_tokens(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    value = positive_int_config(
        config,
        "react_decision_max_tokens",
        DEFAULT_REACT_DECISION_MAX_TOKENS,
    )
    return min(value, MAX_REACT_DECISION_MAX_TOKENS)


def _react_observation_text(
    task: SubTask,
    result: TaskResult,
    format_task_result_context: FormatTaskResultContext,
) -> str:
    return format_task_result_context(
        task.task_id,
        result,
        DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    )


def _react_trace_text(iteration: int, observation: str, action_summary: str) -> str:
    lines = [
        f"ReAct step {iteration}",
        f"Observation: {observation}",
        f"Action: {action_summary}",
    ]
    return "\n".join(lines) + "\n"


def _react_action_summary(decision: ReactDecision) -> str:
    summaries: list[str] = []
    for action in decision.actions:
        action_type = action.get("type")
        if action_type == "add_task" and isinstance(action.get("task"), Mapping):
            task = action["task"]
            task_id = task.get("task_id", "<unknown>")
            agent_id = task.get("agent_id", "<unknown>")
            summaries.append(f"add_task {task_id} -> @{agent_id}")
        elif action_type == "update_task":
            summaries.append(f"update_task {action.get('task_id', '<unknown>')}")
        elif action_type == "skip_task":
            summaries.append(f"skip_task {action.get('task_id', '<unknown>')}")
        elif action_type == "finish":
            summaries.append(f"finish: {action.get('reason', 'done')}")
        else:
            summaries.append(str(action_type or "unknown"))
    return "; ".join(summaries) if summaries else "continue"


async def _react_decision(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext,
    iteration: int,
    max_iterations: int,
    observation: str,
    *,
    format_task_result_context: FormatTaskResultContext,
    latest_user_request: LatestUserRequest,
    positive_int_config: PositiveIntConfig,
    agent_id_list: AgentIdList,
    error_reason: ErrorReason,
) -> ReactDecision:
    gateway = _react_gateway(config, positive_int_config)
    parts: list[str] = []
    try:
        async for chunk in gateway.stream(
            _react_messages(
                config,
                messages,
                tasks,
                task_states,
                run_context,
                iteration,
                max_iterations,
                observation,
                format_task_result_context=format_task_result_context,
                latest_user_request=latest_user_request,
                agent_id_list=agent_id_list,
            ),
            system_prompt=_react_system_prompt(),
            config=_react_config(config, positive_int_config),
        ):
            if chunk.event_type == "delta":
                parts.append(chunk.text_delta or chunk.code_delta or "")
            elif chunk.event_type == "error":
                raise ReactDecisionError(error_reason(chunk))
    except ReactDecisionError:
        raise
    except Exception as exc:
        raise ReactDecisionError(str(exc)) from exc
    return _parse_react_decision("".join(parts).strip())


def _react_gateway(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> Any:
    gateway = config.get("react_gateway", config.get("replanner_gateway"))
    if gateway is not None:
        return gateway
    backend = config.get("planner_model_backend", config.get("model_backend", "claude"))
    if not isinstance(backend, str) or not backend.strip():
        raise ReactDecisionError("replanner model backend must be a string")
    return ModelGateway(
        backend,
        default_config=_react_config(config, positive_int_config),
        agent_id="orchestrator-react",
        system_prompt=_react_system_prompt(),
    )


def _react_config(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> dict[str, Any]:
    raw_config = config.get("orchestrator_llm_config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ReactDecisionError("orchestrator_llm_config must be an object")
    react_config: dict[str, Any] = {
        "temperature": 0,
        "max_tokens": _react_decision_max_tokens(config, positive_int_config),
    }
    react_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in react_config:
            react_config[key] = config[key]
    return react_config


def _react_system_prompt() -> str:
    return (
        "You are AgentHub's Orchestrator ReAct replanner. "
        "Return strict JSON only. Do not include markdown. Do not include thought, "
        "chain_of_thought, hidden reasoning, or private analysis. "
        "Choose actions from add_task, update_task, skip_task, finish."
    )


def _react_messages(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext,
    iteration: int,
    max_iterations: int,
    observation: str,
    *,
    format_task_result_context: FormatTaskResultContext,
    latest_user_request: LatestUserRequest,
    agent_id_list: AgentIdList,
) -> list[ChatMessage]:
    payload = {
        "user_request": latest_user_request(messages),
        "iteration": iteration,
        "max_iterations": max_iterations,
        "available_agents": _available_agent_summaries(config, agent_id_list),
        "task_graph": [
            {
                "task_id": task.task_id,
                "agent_id": task.agent_id,
                "title": task.title,
                "instruction": task.instruction,
                "depends_on": list(task.depends_on),
                "priority": task.priority,
                "expected_output": task.expected_output,
                "include_history": task.include_history,
                "state": task_states.get(task.task_id, TaskState.PENDING).value,
            }
            for task in tasks
        ],
        "recent_observation": observation,
        "results": [
            format_task_result_context(
                task_id,
                result,
                DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
            )
            for task_id, result in run_context.results.items()
        ],
        "required_output": {
            "actions": [
                {
                    "type": "add_task|update_task|skip_task|finish",
                    "task": "required for add_task",
                    "task_id": "required for update_task/skip_task",
                    "patch": "object for update_task",
                    "reason": "string for skip_task/finish",
                }
            ],
            "summary": "short non-private decision summary",
        },
    }
    return [ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False))]


def _available_agent_summaries(
    config: Mapping[str, Any],
    agent_id_list: AgentIdList,
) -> list[dict[str, Any]]:
    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        summaries: list[dict[str, Any]] = []
        for item in available_agents:
            if not isinstance(item, Mapping):
                continue
            raw_id = item.get("agent_id", item.get("id"))
            if not isinstance(raw_id, str) or not raw_id.strip() or raw_id == "orchestrator":
                continue
            summaries.append(
                {
                    "id": raw_id.strip(),
                    "name": item.get("name"),
                    "provider": item.get("provider"),
                    "capabilities": item.get("capabilities"),
                }
            )
        if summaries:
            return summaries
    return [{"id": agent_id} for agent_id in _allowed_agent_ids(config, agent_id_list)]


def _parse_react_decision(text: str) -> ReactDecision:
    if not text:
        raise ReactDecisionError("empty_react_decision")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReactDecisionError("invalid_react_json") from exc
    if not isinstance(payload, Mapping):
        raise ReactDecisionError("react decision must be an object")
    raw_actions = payload.get("actions")
    if not isinstance(raw_actions, list):
        raise ReactDecisionError("react decision actions must be a list")
    actions: list[Mapping[str, Any]] = []
    for raw_action in raw_actions:
        if not isinstance(raw_action, Mapping):
            raise ReactDecisionError("react action must be an object")
        actions.append(raw_action)
    summary = payload.get("summary")
    return ReactDecision(actions=actions, summary=summary if isinstance(summary, str) else "")


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
        }
        for key in (
            "agent_id",
            "title",
            "instruction",
            "depends_on",
            "priority",
            "expected_output",
            "include_history",
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
    ids = _agent_ids_from_available_agents(config.get("available_agents"))
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
