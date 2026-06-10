"""dispatch_agent argument validation and result construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.agents.orchestrator._internal.tools.catalog import available_agent_ids
from app.agents.orchestrator._internal.tools.streaming import truncate
from app.agents.orchestrator._internal.tools.types import (
    DEFAULT_TOOL_RESULT_MAX_CHARS,
    OrchestratorToolCall,
    OrchestratorToolResult,
)
from app.agents.orchestrator.types import OrchestratorRunContext, SubTask, TaskResult

FormatTaskResultContext = Callable[[str, TaskResult, int], str]


def _dispatch_task_from_call(
    call: OrchestratorToolCall,
    config: Mapping[str, Any],
) -> SubTask | OrchestratorToolResult:
    agent_id = _required_str(call.arguments.get("agent_id"))
    title = _required_str(call.arguments.get("title"))
    instruction = _required_str(call.arguments.get("instruction"))
    if agent_id is None or title is None or instruction is None:
        return OrchestratorToolResult(
            status="error",
            output="dispatch_agent requires agent_id, title, and instruction",
            error_code="invalid_arguments",
        )
    allowed_agents = set(available_agent_ids(config))
    if agent_id == "orchestrator" or agent_id not in allowed_agents:
        return OrchestratorToolResult(
            status="error",
            output=f"agent is not available for this conversation: {agent_id}",
            error_code="agent_not_allowed",
        )
    task_id = _task_id(call.arguments.get("task_id"), call.call_id)
    return SubTask(
        task_id=task_id,
        agent_id=agent_id,
        title=title,
        instruction=instruction,
        expected_output=_optional_str(call.arguments.get("expected_output")),
        include_history=_optional_bool(call.arguments.get("include_history"), True),
        task_type=_optional_task_type(call.arguments.get("task_type")),
    )

def _dispatch_observation_result(
    task_id: str,
    run_context: OrchestratorRunContext,
    *,
    result_max_chars: int,
    format_task_result_context: FormatTaskResultContext,
) -> OrchestratorToolResult:
    result = run_context.results.get(task_id)
    if result is None:
        return OrchestratorToolResult(
            status="error",
            output="dispatch_agent did not produce a task result",
            error_code="dispatch_failed",
        )
    output = truncate(
        _format_dispatch_observation(task_id, result, format_task_result_context),
        result_max_chars,
    )
    return OrchestratorToolResult(
        status="ok" if result.final_state.value == "succeeded" else "error",
        output=output[0],
        error_code=None if result.final_state.value == "succeeded" else result.final_state.value,
        output_truncated=output[1],
    )

def _format_dispatch_observation(
    task_id: str,
    result: TaskResult,
    format_task_result_context: FormatTaskResultContext,
) -> str:
    return format_task_result_context(task_id, result, DEFAULT_TOOL_RESULT_MAX_CHARS)

def _task_id(value: object, call_id: str) -> str:
    if isinstance(value, str) and value.strip():
        return _safe_task_id(value.strip())
    return _safe_task_id(call_id)

def _safe_task_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in value)
    return safe.strip(".-") or "tool-task"

def _required_str(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()

def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None

def _optional_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _optional_task_type(value: object) -> str:
    if not isinstance(value, str):
        return "implementation"
    normalized = value.strip() or "implementation"
    if normalized not in {
        "implementation",
        "review",
        "repair",
        "conversation",
        "dialogue_turn",
    }:
        return "implementation"
    return normalized
