"""LLM-backed task planning helpers for OrchestratorAdapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

TASK_PLAN_TOOL_NAME = "submit_task_plan"
DEFAULT_PLANNER_MAX_TOKENS = 2048

PLANNER_SYSTEM_PROMPT = """You are AgentHub's Orchestrator planner.
Create a concise task plan for the available agents only.
You must call submit_task_plan exactly once when the tool is available.
If tools are unavailable, output only JSON in the same shape as the tool input.
Each task must target exactly one available agent_id.
Each task instruction must be self-contained and must not ask one sub-agent to contact
other agents. The backend will dispatch tasks; sub-agents only complete their own task.
"""


@dataclass(frozen=True, slots=True)
class PlannerOutput:
    payload: Any
    allowed_agent_ids: set[str]


def llm_planning_enabled(config: Mapping[str, Any]) -> bool:
    if config.get("planner_gateway") is not None:
        return True
    if config.get("llm_planning") is True:
        return True
    return isinstance(config.get("orchestrator_llm_config"), Mapping)


async def plan_task_payload(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    user_request: str,
) -> PlannerOutput:
    allowed_agent_ids = _available_agent_ids(config)
    if not allowed_agent_ids:
        raise ValueError(
            "missing_task_plan: config.tasks or config.managed_agent_ids is required"
        )

    planner_gateway = _planner_gateway(config, system_prompt)
    payload = await _collect_planner_payload(
        planner_gateway,
        config,
        messages,
        system_prompt,
        user_request,
        allowed_agent_ids,
    )
    return PlannerOutput(payload=payload, allowed_agent_ids=set(allowed_agent_ids))


async def _collect_planner_payload(
    planner_gateway: Any,
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    user_request: str,
    allowed_agent_ids: list[str],
) -> Any:
    planner_text: list[str] = []
    tool_payload: dict[str, Any] | None = None

    async for chunk in _planner_stream(
        planner_gateway,
        config,
        messages,
        system_prompt,
        user_request,
        allowed_agent_ids,
    ):
        if chunk.event_type == "tool_call" and chunk.tool_name == TASK_PLAN_TOOL_NAME:
            tool_payload = chunk.tool_arguments or {}
        elif chunk.event_type == "delta":
            planner_text.append(chunk.text_delta or chunk.code_delta or "")
        elif chunk.event_type == "error":
            raise ValueError(
                f"missing_task_plan: planner failed: {_planner_error_detail(chunk)}"
            )

    if tool_payload is not None:
        return tool_payload
    text = "".join(planner_text)
    if not text.strip():
        raise ValueError("missing_task_plan: empty_planner_output")
    return _json_payload_from_text(text)


async def _planner_stream(
    planner_gateway: Any,
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    user_request: str,
    allowed_agent_ids: list[str],
) -> AsyncIterator[StreamChunk]:
    async for chunk in planner_gateway.stream(
        _planner_messages(config, messages, user_request, allowed_agent_ids),
        system_prompt=_planner_system_prompt(system_prompt),
        config=_planner_config(config),
        tools=[_task_plan_tool()],
    ):
        yield chunk


def _planner_gateway(config: Mapping[str, Any], system_prompt: str | None) -> Any:
    gateway = config.get("planner_gateway")
    if gateway is not None:
        return gateway

    backend = config.get("planner_model_backend", config.get("model_backend", "claude"))
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("invalid_task_plan: planner model backend must be a string")

    return ModelGateway(
        backend,
        default_config=_planner_config(config),
        agent_id="orchestrator-planner",
        system_prompt=_planner_system_prompt(system_prompt),
    )


def _planner_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw_config = config.get("orchestrator_llm_config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ValueError("invalid_task_plan: orchestrator_llm_config must be an object")

    planner_config: dict[str, Any] = {
        "temperature": 0,
        "max_tokens": DEFAULT_PLANNER_MAX_TOKENS,
        "tool_choice": {"type": "auto"},
    }
    planner_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in planner_config:
            planner_config[key] = config[key]
    return planner_config


def _planner_system_prompt(system_prompt: str | None) -> str:
    if system_prompt:
        return f"{system_prompt}\n\n{PLANNER_SYSTEM_PROMPT}"
    return PLANNER_SYSTEM_PROMPT


def _planner_messages(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    user_request: str,
    allowed_agent_ids: list[str],
) -> list[ChatMessage]:
    _ = messages
    agents = _available_agents_description(config, allowed_agent_ids)
    content = (
        "User request:\n"
        f"{user_request}\n\n"
        "Available agents:\n"
        f"{agents}\n\n"
        "Return tasks as {\"tasks\": [...]} using only these agent ids."
    )
    return [ChatMessage(role="user", content=content)]


def _task_plan_tool() -> ToolSpec:
    return ToolSpec(
        name=TASK_PLAN_TOOL_NAME,
        description="Submit the complete task plan for AgentHub sub-agent dispatch.",
        parameters={
            "type": "object",
            "required": ["tasks"],
            "properties": {
                "tasks": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["task_id", "agent_id", "title", "instruction"],
                        "properties": {
                            "task_id": {"type": "string"},
                            "agent_id": {"type": "string"},
                            "title": {"type": "string"},
                            "instruction": {"type": "string"},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                            "priority": {"type": "integer", "default": 0},
                            "expected_output": {"type": "string"},
                        },
                    },
                }
            },
        },
    )


def _available_agent_ids(config: Mapping[str, Any]) -> list[str]:
    ids = _agent_ids_from_available_agents(config.get("available_agents"))
    if ids:
        return ids
    return _agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))


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


def _agent_id_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        agent_id = item.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        result.append(agent_id)
    return result


def _available_agents_description(
    config: Mapping[str, Any],
    allowed_agent_ids: list[str],
) -> str:
    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        lines = _available_agent_lines(available_agents)
        if lines:
            return "\n".join(lines)
    return "\n".join(f"- {agent_id}" for agent_id in allowed_agent_ids)


def _available_agent_lines(available_agents: list[object]) -> list[str]:
    lines: list[str] = []
    for item in available_agents:
        if not isinstance(item, Mapping):
            continue
        raw_id = item.get("agent_id", item.get("id"))
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        line = _available_agent_line(raw_id.strip(), item)
        if line:
            lines.append(line)
    return lines


def _available_agent_line(agent_id: str, item: Mapping[str, Any]) -> str | None:
    if agent_id == "orchestrator":
        return None
    parts = [f"- {agent_id}"]
    name = item.get("name")
    provider = item.get("provider")
    capabilities = item.get("capabilities")
    if isinstance(name, str) and name:
        parts.append(f"name={name}")
    if isinstance(provider, str) and provider:
        parts.append(f"provider={provider}")
    if isinstance(capabilities, list):
        caps = [cap for cap in capabilities if isinstance(cap, str)]
        if caps:
            parts.append(f"capabilities={', '.join(caps)}")
    return " | ".join(parts)


def _json_payload_from_text(text: str) -> Any:
    stripped = _strip_json_fence(text)
    decoder = json.JSONDecoder()
    for start in _json_start_positions(stripped):
        try:
            payload, _ = decoder.raw_decode(stripped[start:])
            return payload
        except json.JSONDecodeError:
            continue
    raise ValueError("invalid_task_plan: invalid_json: planner did not return valid JSON")


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    first_newline = stripped.find("\n")
    last_fence = stripped.rfind("```")
    if first_newline == -1 or last_fence <= first_newline:
        return stripped
    return stripped[first_newline + 1 : last_fence].strip()


def _json_start_positions(text: str) -> list[int]:
    positions = [index for index, char in enumerate(text) if char in "[{"]
    if 0 not in positions:
        positions.insert(0, 0)
    return positions


def _error_reason(chunk: StreamChunk) -> str:
    return chunk.error or chunk.error_code or "unknown error"


def _planner_error_detail(chunk: StreamChunk) -> str:
    if chunk.error_code and chunk.error:
        return f"{chunk.error_code}: {chunk.error}"
    return _error_reason(chunk)
