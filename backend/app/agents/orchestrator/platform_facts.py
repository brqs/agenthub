"""Deterministic platform-fact routing for the orchestrator."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.types import ChatMessage, StreamChunk

PLATFORM_FACT_TYPES = {
    "group_agents",
    "group_models",
    "group_capabilities",
    "self_model",
}
GROUP_AGENT_QUESTION_MARKERS = (
    "当前群聊有哪些agent",
    "当前群聊有哪些成员",
    "当前群聊里有哪些agent",
    "当前群里有哪些agent",
    "当前群聊有什么agent",
    "当前群里有什么agent",
    "当前群聊里有谁",
    "当前群里有谁",
    "群聊有哪些agent",
    "群聊有什么agent",
    "群聊里有谁",
    "群聊成员",
    "群里有哪些agent",
    "群里有哪些成员",
    "群里有什么agent",
    "群里有谁",
    "agents in group",
    "agents are in this group",
    "who is in this group",
    "current group agents",
    "group agents",
)
MODEL_FACT_MARKERS = (
    "模型",
    "model",
    "models",
    "runtime",
    "后端",
    "backend",
)
GROUP_FACT_MARKERS = (
    "当前群聊",
    "当前群里",
    "这个群聊",
    "本群",
    "群里",
    "群聊",
    "group",
)
CAPABILITY_FACT_MARKERS = (
    "能做什么",
    "可以做什么",
    "能力",
    "capabilities",
    "capability",
    "what can",
)
SELF_FACT_MARKERS = (
    "你是什么模型",
    "你用什么模型",
    "你使用什么模型",
    "你是什么后端",
    "你用什么后端",
    "你是什么runtime",
    "what model are you",
    "which model are you",
    "what backend are you",
    "which backend are you using",
    "what runtime are you",
)
MODEL_FOLLOWUP_MARKERS = (
    "还有哪些模型",
    "还有什么模型",
    "还有哪些",
    "还有什么",
    "what other models",
    "which other models",
    "any other models",
)
PLATFORM_FACT_CLASSIFIER_PROMPT = """Classify whether the user's latest message asks
for an AgentHub platform fact. Return strict JSON only:
{"intent":"platform_fact"|"other","fact_type":"group_agents"|"group_models"|"group_capabilities"|"self_model"|null,"confidence":0.0}
Do not answer the user. Do not include markdown.
"""

LatestUserRequest = Callable[[list[ChatMessage]], str]
AgentIdList = Callable[[object], list[str]]
ExplicitAgentMentions = Callable[[list[str], str], list[str]]
HasTaskIntent = Callable[[str], bool]
ErrorReason = Callable[[StreamChunk], str]


async def platform_fact_intent(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    *,
    latest_user_request: LatestUserRequest,
    agent_id_list: AgentIdList,
    explicit_agent_mentions: ExplicitAgentMentions,
    has_task_intent: HasTaskIntent,
    error_reason: ErrorReason,
) -> list[str]:
    intent = _rule_platform_fact_intent(
        config,
        messages,
        latest_user_request=latest_user_request,
        agent_id_list=agent_id_list,
        explicit_agent_mentions=explicit_agent_mentions,
        has_task_intent=has_task_intent,
    )
    if intent:
        return intent
    if config.get("platform_fact_classifier_enabled") is True:
        return await _classify_platform_fact_intent(
            config,
            messages,
            error_reason=error_reason,
        )
    return []


def platform_fact_text(config: Mapping[str, Any], fact_types: list[str]) -> str:
    sections: list[str] = []
    for fact_type in fact_types:
        if fact_type == "group_agents":
            sections.append(_group_agents_text(config).strip())
        elif fact_type == "group_models":
            sections.append(_group_models_text(config).strip())
        elif fact_type == "group_capabilities":
            sections.append(_group_capabilities_text(config).strip())
        elif fact_type == "self_model":
            sections.append(_self_model_text(config).strip())
    return "\n\n".join(section for section in sections if section) + "\n"


def _rule_platform_fact_intent(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    *,
    latest_user_request: LatestUserRequest,
    agent_id_list: AgentIdList,
    explicit_agent_mentions: ExplicitAgentMentions,
    has_task_intent: HasTaskIntent,
) -> list[str]:
    user_request = latest_user_request(messages)
    normalized = _strip_orchestrator_mention(user_request).lower()
    compact = _compact_text(normalized)
    has_conversation_agents = bool(_conversation_agents(config))
    agent_ids = agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))
    explicit_mentions = explicit_agent_mentions(agent_ids, user_request)

    if len(explicit_mentions) >= 2 or (explicit_mentions and has_task_intent(normalized)):
        return []

    intents: list[str] = []
    if has_conversation_agents and _is_group_agent_question(normalized, compact):
        intents.append("group_agents")
    if has_conversation_agents and _is_group_capability_question(normalized, compact):
        intents.append("group_capabilities")
    if has_conversation_agents and _matches_model_followup(
        messages,
        latest_user_request=latest_user_request,
    ):
        intents.append("group_models")
    if has_conversation_agents and _is_group_model_question(normalized, compact):
        intents.append("group_models")
    if _is_self_model_question(normalized, compact):
        intents.append("self_model")
    return _dedupe_intents(intents)


def _is_group_agent_question(normalized: str, compact: str) -> bool:
    return _matches_any(normalized, compact, GROUP_AGENT_QUESTION_MARKERS)


def _is_group_model_question(normalized: str, compact: str) -> bool:
    group_model_phrases = (
        "当前群聊有哪些模型",
        "当前群里有哪些模型",
        "这个群聊有哪些模型",
        "本群有哪些模型",
        "群聊有哪些模型",
        "群里有哪些模型",
        "当前群聊支持什么模型",
        "当前群里支持什么模型",
        "这个群聊支持什么模型",
        "本群支持什么模型",
        "群聊支持什么模型",
        "群里支持什么模型",
        "当前群聊支持哪些模型",
        "群聊支持哪些模型",
        "群里支持哪些模型",
        "models in group",
        "group models",
        "available models",
    )
    if _matches_any(normalized, compact, group_model_phrases):
        return True
    return any(
        marker in normalized or marker in compact
        for marker in (
            "当前有哪些模型",
            "有哪些模型",
        )
    )


def _is_self_model_question(normalized: str, compact: str) -> bool:
    if _matches_any(normalized, compact, SELF_FACT_MARKERS):
        return True
    self_markers = ("你", "orchestrator", "you", "your")
    has_self = any(marker in normalized or marker in compact for marker in self_markers)
    has_model = any(marker in normalized or marker in compact for marker in MODEL_FACT_MARKERS)
    return has_self and has_model


def _is_group_capability_question(normalized: str, compact: str) -> bool:
    has_capability = any(
        marker in normalized or marker in compact for marker in CAPABILITY_FACT_MARKERS
    )
    has_group_or_agents = any(
        marker in normalized or marker in compact
        for marker in (*GROUP_FACT_MARKERS, "agent", "agents", "成员")
    )
    return has_capability and has_group_or_agents


def _dedupe_intents(intents: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for intent in intents:
        if intent not in PLATFORM_FACT_TYPES or intent in seen:
            continue
        seen.add(intent)
        result.append(intent)
    return result


def _matches_model_followup(
    messages: list[ChatMessage],
    *,
    latest_user_request: LatestUserRequest,
) -> bool:
    latest = _strip_orchestrator_mention(latest_user_request(messages)).lower()
    latest_compact = _compact_text(latest)
    if not _matches_any(latest, latest_compact, MODEL_FOLLOWUP_MARKERS):
        return False
    return any(
        any(marker in previous for marker in MODEL_FACT_MARKERS)
        for previous in _recent_user_messages_before_latest(messages)
    )


def _recent_user_messages_before_latest(messages: list[ChatMessage]) -> list[str]:
    previous: list[str] = []
    found_latest = False
    for message in reversed(messages):
        if message.role != "user" or not message.content.strip():
            continue
        if not found_latest:
            found_latest = True
            continue
        previous.append(_strip_orchestrator_mention(message.content).lower())
        if len(previous) >= 3:
            break
    return previous


def _matches_any(normalized: str, compact: str, markers: tuple[str, ...]) -> bool:
    return any(marker in normalized or marker in compact for marker in markers)


def _conversation_agents(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = config.get("conversation_agents")
    if not isinstance(value, list):
        return []
    agents: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        agent_id = item.get("id")
        name = item.get("name")
        if not isinstance(agent_id, str) or not agent_id.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        agents.append(item)
    return agents


async def _classify_platform_fact_intent(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    *,
    error_reason: ErrorReason,
) -> list[str]:
    try:
        text = await _collect_platform_fact_classifier_text(
            config,
            messages,
            error_reason=error_reason,
        )
    except Exception:  # noqa: BLE001
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, Mapping):
        return []
    intent = payload.get("intent")
    fact_type = payload.get("fact_type")
    confidence = payload.get("confidence")
    if intent != "platform_fact":
        return []
    if fact_type not in PLATFORM_FACT_TYPES:
        return []
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return []
    if confidence < 0.65:
        return []
    if fact_type != "self_model" and not _conversation_agents(config):
        return []
    return [str(fact_type)]


async def _collect_platform_fact_classifier_text(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    *,
    error_reason: ErrorReason,
) -> str:
    gateway = _platform_fact_classifier_gateway(config)
    parts: list[str] = []
    async for chunk in gateway.stream(
        _platform_fact_classifier_messages(messages),
        system_prompt=PLATFORM_FACT_CLASSIFIER_PROMPT,
        config=_platform_fact_classifier_config(config),
    ):
        if chunk.event_type == "delta":
            parts.append(chunk.text_delta or chunk.code_delta or "")
        elif chunk.event_type == "error":
            raise ValueError(error_reason(chunk))
    return "".join(parts).strip()


def _platform_fact_classifier_gateway(config: Mapping[str, Any]) -> Any:
    gateway = config.get("platform_fact_classifier_gateway")
    if gateway is not None:
        return gateway

    backend = config.get(
        "platform_fact_classifier_model_backend",
        config.get("answer_model_backend", config.get("model_backend", "claude")),
    )
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("invalid_platform_fact_classifier: backend must be a string")
    return ModelGateway(
        backend,
        default_config=_platform_fact_classifier_config(config),
        agent_id="orchestrator-platform-fact-classifier",
        system_prompt=PLATFORM_FACT_CLASSIFIER_PROMPT,
    )


def _platform_fact_classifier_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw_config = config.get("platform_fact_classifier_config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ValueError(
            "invalid_platform_fact_classifier: platform_fact_classifier_config must be an object"
        )
    classifier_config: dict[str, Any] = {
        "temperature": 0,
        "max_tokens": 128,
    }
    classifier_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in classifier_config:
            classifier_config[key] = config[key]
    return classifier_config


def _platform_fact_classifier_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    recent = [
        f"{message.role}: {message.content}"
        for message in messages[-6:]
        if message.role in {"user", "assistant"} and message.content.strip()
    ]
    return [
        ChatMessage(
            role="user",
            content="Recent messages:\n" + "\n".join(recent),
        )
    ]


def _group_agents_text(config: Mapping[str, Any]) -> str:
    agents = _conversation_agents(config)
    lines = [f"当前群聊包含 {len(agents)} 个 agent：", ""]
    for agent in agents:
        agent_id = str(agent["id"])
        name = str(agent["name"])
        provider = agent.get("provider")
        capabilities = agent.get("capabilities")
        detail_parts = [f"id: {agent_id}"]
        if isinstance(provider, str) and provider:
            detail_parts.append(f"provider: {provider}")
        line = f"- {name} ({', '.join(detail_parts)})"
        if isinstance(capabilities, list):
            capability_names = [
                item for item in capabilities if isinstance(item, str) and item.strip()
            ]
            if capability_names:
                line += f" - capabilities: {', '.join(capability_names)}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _group_models_text(config: Mapping[str, Any]) -> str:
    agents = _conversation_agents(config)
    lines = [f"当前群聊包含 {len(agents)} 个 agent；可见的模型/运行时配置如下：", ""]
    for agent in agents:
        name = str(agent["name"])
        agent_id = str(agent["id"])
        details = _agent_model_details(agent)
        lines.append(f"- {name} (id: {agent_id}): {details}")
    return "\n".join(lines) + "\n"


def _agent_model_details(agent: Mapping[str, Any]) -> str:
    provider = _safe_str(agent.get("provider"))
    parts: list[str] = []
    if provider:
        parts.append(f"provider: {provider}")
    for label, key in (
        ("runtime", "runtime"),
        ("model_backend", "model_backend"),
        ("answer_model_backend", "answer_model_backend"),
        ("planner_model_backend", "planner_model_backend"),
        ("qa_model_backend", "qa_model_backend"),
        ("qa_model", "qa_model"),
    ):
        value = _safe_str(agent.get(key))
        if value:
            parts.append(f"{label}: {value}")
    if _safe_str(agent.get("id")) == "orchestrator":
        if not _safe_str(agent.get("answer_model_backend")) and not _safe_str(
            agent.get("model_backend")
        ):
            parts.append("direct answer backend: 未在 AgentHub 配置中暴露")
        if not _safe_str(agent.get("planner_model_backend")) and not _safe_str(
            agent.get("model_backend")
        ):
            parts.append("planner backend: 未在 AgentHub 配置中暴露")
    elif not any(_safe_str(agent.get(key)) for key in _model_detail_keys()):
        parts.append("执行模型: 未在 AgentHub 配置中暴露")
    return "; ".join(parts) if parts else "未在 AgentHub 配置中暴露"


def _group_capabilities_text(config: Mapping[str, Any]) -> str:
    agents = _conversation_agents(config)
    lines = [f"当前群聊包含 {len(agents)} 个 agent；能力配置如下：", ""]
    for agent in agents:
        capabilities = agent.get("capabilities")
        caps = []
        if isinstance(capabilities, list):
            caps = [item for item in capabilities if isinstance(item, str) and item.strip()]
        summary = ", ".join(caps) if caps else "未在 AgentHub 配置中暴露"
        lines.append(f"- {agent['name']} (id: {agent['id']}): {summary}")
    return "\n".join(lines) + "\n"


def _self_model_text(config: Mapping[str, Any]) -> str:
    answer_backend = _config_backend(config, "answer_model_backend")
    planner_backend = _config_backend(config, "planner_model_backend")
    lines = [
        "我是 AgentHub Orchestrator。",
        f"- direct answer backend: {answer_backend}",
        f"- planner backend: {planner_backend}",
    ]
    exact_model = _safe_str(config.get("model"))
    if exact_model:
        lines.append(f"- model: {exact_model}")
    else:
        lines.append("- model: 未在 AgentHub 配置中暴露")
    return "\n".join(lines) + "\n"


def _config_backend(config: Mapping[str, Any], key: str) -> str:
    value = _safe_str(config.get(key))
    if value:
        return value
    fallback = _safe_str(config.get("model_backend"))
    if fallback:
        return fallback
    return "未在 AgentHub 配置中暴露"


def _model_detail_keys() -> tuple[str, ...]:
    return (
        "runtime",
        "model_backend",
        "answer_model_backend",
        "planner_model_backend",
        "qa_model_backend",
        "qa_model",
    )


def _safe_str(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _strip_orchestrator_mention(text: str) -> str:
    return text.replace("@orchestrator", "").replace("＠orchestrator", "").strip()
