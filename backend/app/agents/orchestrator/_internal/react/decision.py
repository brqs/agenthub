"""ReAct model decision request and response parsing."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator._internal.react.graph import _allowed_agent_ids
from app.agents.orchestrator._internal.react.types import ReactDecision, ReactDecisionError
from app.agents.orchestrator.types import (
    DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk

DEFAULT_REACT_DECISION_MAX_TOKENS = 2048
MAX_REACT_DECISION_MAX_TOKENS = 4096

FormatTaskResultContext = Callable[[str, TaskResult, int], str]
LatestUserRequest = Callable[[list[ChatMessage]], str]
PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]
AgentIdList = Callable[[object], list[str]]
ErrorReason = Callable[[StreamChunk], str]


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
