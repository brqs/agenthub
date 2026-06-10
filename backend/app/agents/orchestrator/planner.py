"""LLM-backed task planning helpers for OrchestratorAdapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator._internal.routing.evidence import (
    ORCHESTRATOR_EVIDENCE_HEADER,
)
from app.agents.orchestrator.availability import (
    is_runnable_agent_context,
    runnable_agent_id,
    runnable_agent_ids,
    scoped_runnable_agent_ids,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.services.context.compression import estimate_tokens, truncate_text

TASK_PLAN_TOOL_NAME = "submit_task_plan"
DEFAULT_PLANNER_MAX_TOKENS = 16384
DEFAULT_PLANNER_CONTEXT_MAX_TOKENS = 128_000
PLANNER_CONTEXT_MAX_TOKENS_LIMIT = 1_000_000
PLANNER_MEMORY_CONTEXT_MAX_TOKENS = 32_000
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
    ORCHESTRATOR_EVIDENCE_HEADER,
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
If the user asks for a debate, role-play, roundtable, panel, or group dialogue and
explicitly says not to create files/artifacts, create conversation tasks with empty
expected_output. If the user asks agents to take turns, respond to each other, or
handoff between agents, create dialogue_turn tasks: one task per turn, each assigned
to exactly the speaker for that turn, with depends_on pointing to the previous turn.
Each dialogue_turn instruction must tell that agent to speak only for itself, respond
to prior turns when applicable, and not script another agent's full reply.
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
    source_messages = _planner_source_messages(config, messages)
    max_tokens = _planner_context_max_tokens(config)
    agents = _available_agents_description(config, allowed_agent_ids)
    instruction_section = _planner_instruction_section()
    agents_section = f"Available agents:\n{agents}"
    request_text = _planner_user_request_for_budget(
        user_request,
        max_tokens,
        agents_section,
        instruction_section,
    )
    required_content = (
        f"User request:\n{request_text}\n\n"
        f"{agents_section}\n\n"
        f"{instruction_section}"
    )
    remaining_tokens = max_tokens - estimate_tokens(required_content)

    memory_context = _planner_memory_context(source_messages)
    memory_context_section = _planner_memory_section(memory_context, remaining_tokens)
    remaining_tokens -= estimate_tokens(memory_context_section)

    recent_context_section = _recent_conversation_section(
        source_messages,
        user_request,
        remaining_tokens,
    )
    content = (
        f"User request:\n{request_text}\n\n"
        f"{memory_context_section}"
        f"{agents_section}\n\n"
        f"{recent_context_section}"
        f"{instruction_section}"
    )
    return [ChatMessage(role="user", content=content)]


def _planner_context_max_tokens(config: Mapping[str, Any]) -> int:
    value = config.get("planner_context_max_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return DEFAULT_PLANNER_CONTEXT_MAX_TOKENS
    return min(value, PLANNER_CONTEXT_MAX_TOKENS_LIMIT)


def _planner_source_messages(
    config: Mapping[str, Any],
    fallback_messages: list[ChatMessage],
) -> list[ChatMessage]:
    raw_messages = config.get("planner_context_messages")
    if not isinstance(raw_messages, list):
        return fallback_messages
    parsed: list[ChatMessage] = []
    for raw in raw_messages:
        if isinstance(raw, ChatMessage):
            parsed.append(raw)
            continue
        if isinstance(raw, Mapping):
            role = raw.get("role")
            content = raw.get("content")
            if role in {"user", "assistant", "system"} and isinstance(content, str):
                parsed.append(ChatMessage(role=role, content=content))
    return parsed or fallback_messages


def _planner_instruction_section() -> str:
    return (
        "Port preview/deploy requests must not become sub-agent execution tasks. "
        "Plan static file creation and verification only. Do not plan Node/Express "
        "servers, package.json scripts, server.js, or any runtime port service. "
        "Preserve explicit acceptance requirements from the user request in task "
        "instructions.\n\n"
        "Return tasks as {\"tasks\": [...]} using only these agent ids."
    )


def _planner_user_request_for_budget(
    user_request: str,
    max_tokens: int,
    agents_section: str,
    instruction_section: str,
) -> str:
    fixed_without_request = (
        "User request:\n\n\n"
        f"{agents_section}\n\n"
        f"{instruction_section}"
    )
    request_budget = max_tokens - estimate_tokens(fixed_without_request)
    return _truncate_to_token_budget(
        user_request,
        max(1, request_budget),
        "latest user request",
    )


def _planner_memory_section(memory_context: str, remaining_tokens: int) -> str:
    if not memory_context or remaining_tokens <= 0:
        return ""
    header = "Orchestrator memory signals available to planner:\n"
    body_budget = remaining_tokens - estimate_tokens(header)
    if body_budget <= 0:
        return ""
    label = "planner memory signals"
    memory_budget = min(PLANNER_MEMORY_CONTEXT_MAX_TOKENS, body_budget)
    memory_text = _truncate_to_token_budget(memory_context, memory_budget, label)
    return f"{header}{memory_text}\n\n"


def _recent_conversation_section(
    messages: list[ChatMessage],
    user_request: str,
    remaining_tokens: int,
) -> str:
    if remaining_tokens <= 0:
        return ""
    blocks = _recent_conversation_blocks(messages, user_request)
    if not blocks:
        return ""
    selected: list[str] = []
    used_tokens = estimate_tokens("Recent conversation context:\n")
    omitted = 0
    budget = max(0, remaining_tokens - used_tokens)
    for block in reversed(blocks):
        block_tokens = estimate_tokens(block)
        if block_tokens <= budget:
            selected.append(block)
            budget -= block_tokens
            continue
        if not selected and budget > 0:
            selected.append(
                _truncate_to_token_budget(
                    block,
                    budget,
                    "oldest included planner conversation turn",
                )
            )
            budget = 0
            continue
        omitted += 1
    if not selected:
        return ""
    selected.reverse()
    notice = (
        f"[older planner conversation context omitted: {omitted} messages due to "
        "planner_context_max_tokens]\n"
        if omitted
        else ""
    )
    return "Recent conversation context:\n" + notice + "\n\n".join(selected) + "\n\n"


def _recent_conversation_blocks(
    messages: list[ChatMessage],
    user_request: str,
) -> list[str]:
    last_current_user_index = _latest_user_request_index(messages, user_request)
    blocks: list[str] = []
    for index, message in enumerate(messages):
        if message.role == "system":
            continue
        if index == last_current_user_index:
            continue
        content = message.content.strip()
        if not content:
            continue
        blocks.append(f"[{message.role}]\n{content}")
    return blocks


def _latest_user_request_index(
    messages: list[ChatMessage],
    user_request: str,
) -> int | None:
    normalized_request = user_request.strip()
    fallback_index: int | None = None
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.role != "user":
            continue
        if fallback_index is None:
            fallback_index = index
        if message.content.strip() == normalized_request:
            return index
    return fallback_index if not normalized_request else None


def _truncate_to_token_budget(text: str, max_tokens: int, label: str) -> str:
    if max_tokens <= 0:
        return f"[{label} omitted due to planner_context_max_tokens]"
    if estimate_tokens(text) <= max_tokens:
        return text
    notice = f"[{label} truncated due to planner_context_max_tokens]\n"
    if estimate_tokens(notice) >= max_tokens:
        return notice.strip()
    low = 1
    high = len(text)
    best = notice.strip()
    while low <= high:
        mid = (low + high) // 2
        candidate = notice + truncate_text(text, mid)
        if estimate_tokens(candidate) <= max_tokens:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best


def _planner_memory_context(messages: list[ChatMessage]) -> str:
    sections: list[str] = []
    for message in messages:
        if message.role != "system":
            continue
        for header in PLANNER_MEMORY_SECTION_HEADERS:
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
                                "enum": [
                                    "implementation",
                                    "review",
                                    "repair",
                                    "conversation",
                                    "dialogue_turn",
                                ],
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
