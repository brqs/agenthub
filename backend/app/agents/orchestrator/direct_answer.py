"""Direct-answer path for AgentHub Orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator.streams import (
    attach_agent_id,
    remap_block_index,
    remap_tool_call_id,
)
from app.agents.types import ChatMessage, StreamChunk

DIRECT_ANSWER_SYSTEM_PROMPT = """You are AgentHub's Orchestrator.
Answer simple questions about your identity, configured model backend, capabilities,
and coordination role directly. Do not create a task plan for these answers.
For implementation or artifact-building requests, the backend will use the planner
and dispatch specialist agents instead.
"""

META_QUESTION_MARKERS = (
    "\u4f60\u597d",
    "\u60a8\u597d",
    "\u4f60\u662f\u8c01",
    "\u4f60\u662f\u4ec0\u4e48",
    "\u4f60\u662f\u4ec0\u4e48\u6a21\u578b",
    "\u4f60\u7528\u4ec0\u4e48\u6a21\u578b",
    "\u4ec0\u4e48\u6a21\u578b",
    "\u54ea\u4e2a\u6a21\u578b",
    "\u4f60\u6709\u4ec0\u4e48\u80fd\u529b",
    "\u4f60\u80fd\u505a\u4ec0\u4e48",
    "\u4f60\u7684\u80fd\u529b",
    "\u4f60\u7684\u804c\u8d23",
    "\u4ecb\u7ecd\u4e00\u4e0b",
    "\u81ea\u6211\u4ecb\u7ecd",
    "\u4f60\u4e4b\u524d\u6709\u4ec0\u4e48\u7f16\u7a0b\u4efb\u52a1",
    "\u4e4b\u524d\u6709\u4ec0\u4e48\u7f16\u7a0b\u4efb\u52a1",
    "\u4e4b\u524d\u6709\u4ec0\u4e48\u4efb\u52a1",
    "\u7f16\u7a0b\u4efb\u52a1\u5417",
    "hello",
    "hi",
    "hey",
    "who are you",
    "what model",
    "which model",
    "what runtime",
    "what can you do",
    "your capabilities",
    "introduce yourself",
)


def should_direct_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    *,
    latest_user_request: Callable[[list[ChatMessage]], str],
    agent_id_list: Callable[[object], list[str]],
    explicit_agent_mentions: Callable[[list[str], str], list[str]],
    strip_orchestrator_mention: Callable[[str], str],
    has_task_intent: Callable[[str], bool],
) -> bool:
    if config.get("tasks") is not None:
        return False
    user_request = latest_user_request(messages)
    agent_ids = agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
    if explicit_agent_mentions(agent_ids, user_request):
        return False
    normalized = strip_orchestrator_mention(user_request).lower()
    if has_task_intent(normalized):
        return False
    if _is_simple_greeting(normalized):
        return True
    return any(marker in normalized for marker in META_QUESTION_MARKERS)


def _is_simple_greeting(text: str) -> bool:
    compact = text.strip().strip("!！?？。,.， ")
    return compact in {
        "\u4f60\u597d",
        "\u60a8\u597d",
        "hello",
        "hi",
        "hey",
    }


async def run_direct_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    next_block_index: int,
    *,
    latest_user_request: Callable[[list[ChatMessage]], str],
) -> AsyncIterator[tuple[StreamChunk, int, bool]]:
    try:
        gateway = _answer_gateway(config, system_prompt)
        answer_config = _answer_config(config)
    except ValueError as exc:
        yield StreamChunk(
            event_type="error",
            error_code=_error_code(exc),
            error=str(exc),
            agent_id="orchestrator",
        ), next_block_index, True
        return

    index_map: dict[int, int] = {}
    open_block_index: int | None = None

    try:
        async for chunk in gateway.stream(
            _answer_messages(messages, latest_user_request=latest_user_request),
            system_prompt=_answer_system_prompt(config, system_prompt),
            config=answer_config,
        ):
            if chunk.event_type in {"start", "done"}:
                continue
            if chunk.event_type == "error":
                if open_block_index is not None:
                    yield StreamChunk(
                        event_type="block_end",
                        block_index=open_block_index,
                        agent_id="orchestrator",
                    ), next_block_index, False
                    open_block_index = None
                yield attach_agent_id(chunk, "orchestrator"), next_block_index, True
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                remapped = remap_tool_call_id(chunk, "direct-answer")
                yield attach_agent_id(remapped, "orchestrator"), next_block_index, False
                continue
            if chunk.event_type == "heartbeat":
                yield attach_agent_id(chunk, "orchestrator"), next_block_index, False
                continue
            if chunk.event_type not in {"block_start", "delta", "block_end"}:
                continue
            remapped, next_block_index = remap_block_index(
                chunk,
                index_map,
                next_block_index,
            )
            if remapped.event_type == "block_start":
                open_block_index = remapped.block_index
            elif remapped.event_type == "block_end":
                open_block_index = None
            yield attach_agent_id(remapped, "orchestrator"), next_block_index, False
    except Exception as exc:
        if open_block_index is not None:
            yield StreamChunk(
                event_type="block_end",
                block_index=open_block_index,
                agent_id="orchestrator",
            ), next_block_index, False
        yield StreamChunk(
            event_type="error",
            error_code="upstream_error",
            error=str(exc),
            agent_id="orchestrator",
        ), next_block_index, True


def _answer_gateway(config: Mapping[str, Any], system_prompt: str | None) -> Any:
    gateway = config.get("answer_gateway")
    if gateway is not None:
        return gateway

    backend = config.get("answer_model_backend", config.get("model_backend", "claude"))
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("invalid_answer_config: answer model backend must be a string")
    return ModelGateway(
        backend,
        default_config=_answer_config(config),
        agent_id="orchestrator-answer",
        system_prompt=_answer_system_prompt(config, system_prompt),
    )


def _answer_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw_config = config.get("orchestrator_answer_config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ValueError(
            "invalid_answer_config: orchestrator_answer_config must be an object"
        )

    answer_config: dict[str, Any] = {
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    answer_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in answer_config:
            answer_config[key] = config[key]
    return answer_config


def _answer_system_prompt(config: Mapping[str, Any], system_prompt: str | None) -> str:
    backend = config.get("answer_model_backend", config.get("model_backend", "claude"))
    backend_name = backend if isinstance(backend, str) and backend else "claude"
    prompt = (
        f"{DIRECT_ANSWER_SYSTEM_PROMPT}\n"
        f"Configured answer backend: {backend_name}.\n"
        "If asked what model you are, answer as AgentHub Orchestrator and mention "
        "that your direct answers use the configured ModelGateway backend."
    )
    if system_prompt:
        return f"{system_prompt}\n\n{prompt}"
    return prompt


def _answer_messages(
    messages: list[ChatMessage],
    *,
    latest_user_request: Callable[[list[ChatMessage]], str],
) -> list[ChatMessage]:
    user_request = latest_user_request(messages)
    return [
        ChatMessage(
            role="user",
            content=(
                "Answer this user message directly as AgentHub Orchestrator. "
                "Do not create or describe a task plan.\n\n"
                f"User message:\n{user_request}"
            ),
        )
    ]


def _error_code(exc: ValueError) -> str:
    message = str(exc)
    if ":" in message:
        return message.split(":", 1)[0]
    return "invalid_request"
