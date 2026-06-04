"""User-visible platform-fact rendering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.routing.platform_facts.common import (
    conversation_agents,
)


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


def _group_agents_text(config: Mapping[str, Any]) -> str:
    agents = conversation_agents(config)
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
    agents = conversation_agents(config)
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
    agents = conversation_agents(config)
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
