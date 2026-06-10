"""Direct-chat routing for external runtime agents."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from app.agents.external.runtime_budget import (
    RuntimeBudget,
    RuntimeBudgetConfig,
    RuntimeTimeoutError,
    iter_with_runtime_budget,
)
from app.agents.model_gateway import ModelGateway
from app.agents.types import ChatMessage, StreamChunk

Route = Literal["direct_chat", "runtime", "disabled"]

DEFAULT_QA_BACKEND = "deepseek"
DEFAULT_QA_MAX_TOKENS = 8192
DEFAULT_CLASSIFIER_MAX_TOKENS = 128
DEFAULT_QA_TEMPERATURE = 0.2
DEFAULT_QA_REQUEST_TIMEOUT_SECONDS = 20.0
DEFAULT_QA_STREAM_IDLE_TIMEOUT_SECONDS = 10.0
DEFAULT_QA_STREAM_MAX_RUNTIME_SECONDS = 45.0
DEFAULT_QA_STREAM_HEARTBEAT_SECONDS = 5.0
DIRECT_CHAT_CONFIDENCE_THRESHOLD = 0.65

CLASSIFIER_PROMPT = """Classify the latest user request for an external coding agent.

Return strict JSON only:
{"route":"direct_chat","confidence":0.92,"reason":"short reason"}

Rules:
- Classify only the latest user message; previous messages are context.
- Use "direct_chat" for general Q&A, explanation, discussion, and short examples
  that do not require workspace access.
- Use "runtime" when the request needs files, workspace state, shell commands,
  tests, debugging, artifacts, preview, deploy, or repository analysis.
- If unsure, choose "runtime".
- Do not answer the user's question."""


@dataclass(frozen=True)
class DirectChatDecision:
    route: Route
    stream: AsyncIterator[StreamChunk] | None = None
    reason: str | None = None


async def maybe_stream_direct_chat(
    *,
    agent_id: str,
    provider: str,
    messages: list[ChatMessage],
    system_prompt: str | None,
    config: dict[str, Any],
) -> DirectChatDecision:
    """Return a direct-chat stream when the latest request is pure Q&A."""
    if not _bool_config(config, "qa_short_circuit_enabled", True):
        return DirectChatDecision(route="disabled", reason="qa_short_circuit_disabled")

    classifier = await _classify(messages, system_prompt, config)
    if classifier.route != "direct_chat":
        return classifier

    return DirectChatDecision(
        route="direct_chat",
        stream=_stream_direct_answer(
            agent_id=agent_id,
            provider=provider,
            messages=messages,
            system_prompt=system_prompt,
            config=config,
        ),
        reason=classifier.reason,
    )


async def _classify(
    messages: list[ChatMessage],
    system_prompt: str | None,
    config: dict[str, Any],
) -> DirectChatDecision:
    try:
        text = await _collect_model_text(
            messages=_classifier_messages(messages, system_prompt),
            system_prompt=CLASSIFIER_PROMPT,
            config=_classifier_config(config),
            backend=_qa_backend(config),
            agent_id="external-direct-chat-classifier",
        )
        parsed = _parse_classifier_json(text)
    except Exception as exc:  # noqa: BLE001
        return DirectChatDecision(route="runtime", reason=f"classifier_failed:{type(exc).__name__}")

    if parsed is None:
        return DirectChatDecision(route="runtime", reason="classifier_invalid_json")
    if parsed["route"] == "runtime":
        return DirectChatDecision(route="runtime", reason=parsed["reason"])
    if parsed["confidence"] < DIRECT_CHAT_CONFIDENCE_THRESHOLD:
        return DirectChatDecision(route="runtime", reason="classifier_low_confidence")
    return DirectChatDecision(route="direct_chat", reason=parsed["reason"])


async def _collect_model_text(
    *,
    messages: list[ChatMessage],
    system_prompt: str | None,
    config: dict[str, Any],
    backend: str,
    agent_id: str,
) -> str:
    gateway = ModelGateway(
        backend,
        default_config=config,
        agent_id=agent_id,
        system_prompt=system_prompt,
    )
    parts: list[str] = []
    budget = RuntimeBudget(_qa_stream_budget_config(config))
    async for chunk in iter_with_runtime_budget(
        gateway.stream(messages, system_prompt=system_prompt, config=config),
        budget,
        agent_id=agent_id,
        provider=backend,
    ):
        if chunk.event_type == "error":
            raise RuntimeError(chunk.error or chunk.error_code or "classifier error")
        if chunk.text_delta:
            parts.append(chunk.text_delta)
        if chunk.code_delta:
            parts.append(chunk.code_delta)
    return "".join(parts).strip()


async def _stream_direct_answer(
    *,
    agent_id: str,
    provider: str,
    messages: list[ChatMessage],
    system_prompt: str | None,
    config: dict[str, Any],
) -> AsyncIterator[StreamChunk]:
    gateway = ModelGateway(
        _qa_backend(config),
        default_config=_answer_config(config),
        agent_id=agent_id,
        system_prompt=_direct_answer_system_prompt(system_prompt),
    )
    open_block_index: int | None = None
    stream = iter_with_runtime_budget(
        gateway.stream(
            messages,
            system_prompt=_direct_answer_system_prompt(system_prompt),
            config=_answer_config(config),
        ),
        RuntimeBudget(_qa_stream_budget_config(config)),
        agent_id=agent_id,
        provider=provider,
    )
    try:
        async for chunk in stream:
            if chunk.event_type == "start":
                continue
            if chunk.event_type == "block_start":
                open_block_index = chunk.block_index
            elif chunk.event_type == "block_end":
                open_block_index = None
            elif chunk.event_type in {"done", "error"}:
                open_block_index = None
            yield _external_chunk(chunk, agent_id=agent_id, provider=provider)
    except RuntimeTimeoutError as exc:
        if open_block_index is not None:
            yield StreamChunk(event_type="block_end", block_index=open_block_index)
        yield StreamChunk(
            event_type="error",
            agent_id=agent_id,
            error_code="direct_chat_timeout",
            error=str(exc),
            metadata={"provider": provider, "retryable": False},
        )
    except asyncio.CancelledError:
        raise


def _external_chunk(
    chunk: StreamChunk,
    *,
    agent_id: str,
    provider: str,
) -> StreamChunk:
    if chunk.event_type not in {"done", "error"}:
        return chunk

    metadata = dict(chunk.metadata or {})
    metadata.setdefault("provider", provider)
    return chunk.model_copy(update={"agent_id": agent_id, "metadata": metadata})


def _classifier_messages(
    messages: list[ChatMessage],
    system_prompt: str | None,
) -> list[ChatMessage]:
    recent = messages[-8:]
    latest_user = _latest_user_content(messages)
    context = "\n\n".join(
        [
            f"External agent system prompt summary:\n{(system_prompt or '')[:1200]}",
            "Recent conversation:\n" + "\n".join(
                f"{message.role}: {message.content[:1600]}" for message in recent
            ),
            f"Latest user message:\n{latest_user}",
        ]
    )
    return [ChatMessage(role="user", content=context)]


def _direct_answer_system_prompt(system_prompt: str | None) -> str:
    lines = [
        "You are answering in direct-chat mode for an AgentHub external coding agent.",
        "Do not read or write workspace files. Do not call tools. Do not suggest "
        "preview or deploy server commands.",
        "Answer the latest user message directly and concisely.",
    ]
    if system_prompt:
        lines.append(system_prompt)
    return "\n".join(lines)


def _parse_classifier_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    route = value.get("route")
    confidence = value.get("confidence")
    reason = value.get("reason")
    if route not in {"direct_chat", "runtime"}:
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return None
    if confidence < 0 or confidence > 1:
        return None
    if not isinstance(reason, str):
        reason = ""
    return {"route": route, "confidence": float(confidence), "reason": reason[:200]}


def _qa_backend(config: dict[str, Any]) -> str:
    value = config.get("qa_model_backend")
    return value if isinstance(value, str) and value else DEFAULT_QA_BACKEND


def _classifier_config(config: dict[str, Any]) -> dict[str, Any]:
    model = config.get("qa_classifier_model") or config.get("qa_model")
    return _gateway_config(
        model=model,
        max_tokens=config.get("qa_classifier_max_tokens", DEFAULT_CLASSIFIER_MAX_TOKENS),
        temperature=config.get("qa_temperature", DEFAULT_QA_TEMPERATURE),
        request_timeout_seconds=config.get(
            "qa_request_timeout_seconds",
            DEFAULT_QA_REQUEST_TIMEOUT_SECONDS,
        ),
    )


def _answer_config(config: dict[str, Any]) -> dict[str, Any]:
    return _gateway_config(
        model=config.get("qa_model"),
        max_tokens=config.get("qa_max_tokens", DEFAULT_QA_MAX_TOKENS),
        temperature=config.get("qa_temperature", DEFAULT_QA_TEMPERATURE),
        request_timeout_seconds=config.get(
            "qa_request_timeout_seconds",
            DEFAULT_QA_REQUEST_TIMEOUT_SECONDS,
        ),
    )


def _gateway_config(
    *,
    model: object,
    max_tokens: object,
    temperature: object,
    request_timeout_seconds: object,
) -> dict[str, Any]:
    gateway_config: dict[str, Any] = {
        "max_tokens": max_tokens,
        "temperature": temperature,
        "request_timeout_seconds": request_timeout_seconds,
        "max_retries": 0,
    }
    if isinstance(model, str) and model:
        gateway_config["model"] = model
    return gateway_config


def _qa_stream_budget_config(config: dict[str, Any]) -> RuntimeBudgetConfig:
    return RuntimeBudgetConfig(
        max_runtime_seconds=_positive_float_config(
            config.get("qa_stream_max_runtime_seconds"),
            DEFAULT_QA_STREAM_MAX_RUNTIME_SECONDS,
        ),
        idle_timeout_seconds=_positive_float_config(
            config.get("qa_stream_idle_timeout_seconds"),
            DEFAULT_QA_STREAM_IDLE_TIMEOUT_SECONDS,
        ),
        heartbeat_interval_seconds=_positive_float_config(
            config.get("qa_stream_heartbeat_seconds"),
            DEFAULT_QA_STREAM_HEARTBEAT_SECONDS,
        ),
    )


def _positive_float_config(value: object, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    parsed = float(value)
    return parsed if parsed > 0 else default


def _bool_config(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key)
    return value if isinstance(value, bool) else default


def _latest_user_content(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""
