"""LLM-backed task planning helpers for OrchestratorAdapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator.availability import (
    is_runnable_agent_context,
    runnable_agent_id,
    runnable_agent_ids,
    scoped_runnable_agent_ids,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

TASK_PLAN_TOOL_NAME = "submit_task_plan"
DEFAULT_PLANNER_MAX_TOKENS = 2048
AGENT_CAPABILITY_PROFILE_V2_HEADER = (
    "Agent capability profile v2 from recent user Orchestrator runs:"
)
USER_PREFERENCE_MEMORY_HEADER = (
    "User preference memory from recent Orchestrator runs:"
)
AGENT_CAPABILITY_PROFILE_HEADER = (
    "Agent capability profile from recent Orchestrator runs:"
)
ORCHESTRATOR_MEMORY_HEADER = "Previous Orchestrator structured memory:"
MEMORYHUB_CONTEXT_HEADER = "MemoryHub mounted context:"
PLANNER_MEMORY_SECTION_HEADERS = (
    MEMORYHUB_CONTEXT_HEADER,
    AGENT_CAPABILITY_PROFILE_V2_HEADER,
    USER_PREFERENCE_MEMORY_HEADER,
    AGENT_CAPABILITY_PROFILE_HEADER,
    ORCHESTRATOR_MEMORY_HEADER,
)

PLANNER_SYSTEM_PROMPT = """You are AgentHub's Orchestrator planner.
Create a concise task plan for the available agents only.
You must call submit_task_plan exactly once when the tool is available.
If tools are unavailable, output only JSON in the same shape as the tool input.
Each task must target exactly one available agent_id. Do not assign tasks to agent ids
outside the available agents list, even if memory mentions them.
When assigning tasks, prefer agents whose user-scope v2 capability profile shows
stronger recent success for the requested task type, artifact kind, review, or
repair pattern. Use current-conversation capability profile evidence as the tie
breaker when it is recent and high confidence. User instructions in the current
request, including explicit agent, technology, or style choices, override historical
profile and preference memory. When the profile clearly shows one available agent
recently succeeded and another failed for the matching work, assign the clearly
stronger agent unless the user explicitly selects an agent or task constraints
require otherwise. Do not probe a weaker agent first and rely on fallback when the
profile already provides clear evidence.
Each task instruction must be self-contained and must not ask one sub-agent to contact
other agents. The backend will dispatch tasks; sub-agents only complete their own task.
Assign planning, implementation, verification, review, repair, and escalation work by
matching the request to each available agent's profile, strengths, weaknesses, and
preferred task types.
When the user explicitly asks for two agents, multiple agents, or parallel development,
split implementation work across distinct implementation-capable agents when available
unless the request explicitly names a specific agent.
When available agent lines include planning_profile, strengths, weaknesses, or
preferred_task_types, use those fields as the primary routing evidence. Do not infer
a default lead, reviewer, implementer, or escalation owner from provider or agent id
alone; choose each agent only when the request and profile match that task.
Preserve every explicit deliverable and acceptance requirement from the user request in
the relevant generation and verification task instructions. A random theme may only add
style; it must not replace requested sections, files, or checks.
For frontend development demo requests, instruct the generator to create a static
index.html, styles.css, and app.js that visibly includes any requested demo sections.
Do not create tasks that start, deploy, preview, or manage long-running port services.
Do not ask sub-agents to create server.js, package.json server scripts, Express/Node
servers, Vite/Next dev servers, or server dependencies just to satisfy preview/deploy.
If the user asks for preview/deploy on a port, plan only file generation and content
verification. Put any preview/deploy handling in the final platform explanation, not
as a sub-agent execution task.
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
    agents = _available_agents_description(config, allowed_agent_ids)
    memory_context = _planner_memory_context(messages)
    memory_context_section = (
        "Orchestrator memory signals available to planner:\n"
        f"{memory_context}\n\n"
        if memory_context
        else ""
    )
    content = (
        "User request:\n"
        f"{user_request}\n\n"
        f"{memory_context_section}"
        "Available agents:\n"
        f"{agents}\n\n"
        "Port preview/deploy requests must not become sub-agent execution tasks. "
        "Plan static file creation and verification only. Do not plan Node/Express "
        "servers, package.json scripts, server.js, or any runtime port service. "
        "Preserve explicit acceptance requirements from the user request in task "
        "instructions.\n\n"
        "Return tasks as {\"tasks\": [...]} using only these agent ids."
    )
    return [ChatMessage(role="user", content=content)]


def _planner_memory_context(messages: list[ChatMessage]) -> str:
    sections: list[str] = []
    for message in messages:
        if message.role != "system":
            continue
        for header in (
            MEMORYHUB_CONTEXT_HEADER,
            AGENT_CAPABILITY_PROFILE_V2_HEADER,
            USER_PREFERENCE_MEMORY_HEADER,
            AGENT_CAPABILITY_PROFILE_HEADER,
        ):
            section = _memory_section(message.content, header)
            if section and section not in sections:
                sections.append(section)
    return "\n\n".join(sections)


def _memory_section(content: str, header: str) -> str:
    start = content.find(header)
    if start < 0:
        return ""
    end_candidates = [
        index
        for candidate in PLANNER_MEMORY_SECTION_HEADERS
        if candidate != header
        for index in [content.find(f"\n\n{candidate}", start + len(header))]
        if index >= 0
    ]
    end = min(end_candidates) if end_candidates else len(content)
    return content[start:end].strip()


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
                            "task_type": {
                                "type": "string",
                                "enum": ["implementation", "review", "repair"],
                                "default": "implementation",
                            },
                            "review_of": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                            "handoff_reason": {"type": "string"},
                        },
                    },
                }
            },
        },
    )


def _available_agent_ids(config: Mapping[str, Any]) -> list[str]:
    scoped_ids = scoped_runnable_agent_ids(config)
    if scoped_ids is not None:
        return scoped_ids
    return _agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))


def _agent_ids_from_available_agents(value: object) -> list[str]:
    return runnable_agent_ids(value)


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
        if not isinstance(item, Mapping) or not is_runnable_agent_context(item):
            continue
        agent_id = runnable_agent_id(item)
        if agent_id is None:
            continue
        line = _available_agent_line(agent_id, item)
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
    _append_text_part(parts, item, "planning_profile")
    _append_list_part(parts, item, "planning_strengths", "strengths")
    _append_list_part(parts, item, "planning_weaknesses", "weaknesses")
    _append_list_part(parts, item, "preferred_task_types", "preferred_task_types")
    _append_list_part(parts, item, "allowed_tools", "tools")
    _append_text_part(parts, item, "system_prompt_summary")
    return " | ".join(parts)


def _append_text_part(parts: list[str], item: Mapping[str, Any], key: str) -> None:
    value = _clean_planner_text(item.get(key), 1200)
    if value:
        parts.append(f"{key}={value}")


def _append_list_part(
    parts: list[str],
    item: Mapping[str, Any],
    key: str,
    label: str,
) -> None:
    value = item.get(key)
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [item for item in value if isinstance(item, str)]
    else:
        return
    items = [
        text
        for raw in raw_items
        for text in [_clean_planner_text(raw, 160)]
        if text
    ]
    if items:
        parts.append(f"{label}={', '.join(items[:20])}")


def _clean_planner_text(value: Any, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.replace("\x00", "").split())
    if not text:
        return None
    if len(text) > max_chars:
        return f"{text[:max_chars].rstrip()}..."
    return text


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
