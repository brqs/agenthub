"""Custom-agent request routing helpers for Orchestrator.

This conversational shortcut creates only server Agent wrappers. It must not
expose model keys, MCP JSON, sandbox, commands, or builtin tool allowlists.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from app.agents.config_validation import WRAPPER_MODE

BASE_AGENT_PROVIDERS = {
    "claude-code": "claude_code",
    "codex-helper": "codex",
    "opencode-helper": "opencode",
}

BASE_AGENT_ALIASES = {
    "claude": "claude-code",
    "claude-code": "claude-code",
    "claude_code": "claude-code",
    "claude code": "claude-code",
    "codex": "codex-helper",
    "codex-helper": "codex-helper",
    "codex helper": "codex-helper",
    "opencode": "opencode-helper",
    "opencode-helper": "opencode-helper",
    "opencode helper": "opencode-helper",
}
PROVIDER_ALIASES = {
    "builtin": "builtin",
    "built-in": "builtin",
    "内置": "builtin",
    "claude_code": "claude_code",
    "claude-code": "claude_code",
    "claude code": "claude_code",
    "codex": "codex",
    "opencode": "opencode",
}
MODEL_BACKEND_ALIASES = {
    "claude": "claude",
    "deepseek": "deepseek",
    "openai": "openai",
}

SMART_AGENT_WORD = "\u667a\u80fd\u4f53"
AGENT_WORD = "\u4ee3\u7406"
CREATE_WORDS = ("\u521b\u5efa", "\u65b0\u5efa", "\u65b0\u589e", "create")
DO_NOT_JOIN = "\u4e0d\u52a0\u5165"
JOIN = "\u52a0\u5165"
GROUP_CHAT = "\u7fa4\u804a"
CURRENT = "\u5f53\u524d"


def custom_agent_tool_arguments(user_request: str) -> dict[str, Any] | None:
    if not _looks_like_custom_agent_request(user_request):
        return None

    name = _extract_named_value(
        user_request,
        (
            r"(?:name|\u540d\u79f0|\u540d\u5b57)\s*"
            r"(?:is|\u4e3a|\u662f|=|:)\s*"
            r"[\"'\u201c\u201d\u2018\u2019]?([^,，。；;\n\"'\u201c\u201d\u2018\u2019]+)",
        ),
    )
    provider_override = _extract_provider(user_request)
    base_agent_id = _extract_base_agent_id(user_request)
    system_prompt = _extract_named_value(
        user_request,
        (
            r"(?:system_prompt|\u7cfb\u7edf\u63d0\u793a\u8bcd|\u89d2\u8272\u8bbe\u5b9a)"
            r"\s*(?:is|\u4e3a|\u662f|=|:)\s*[\"\u201c](.+?)[\"\u201d]",
            r"(?:system_prompt|\u7cfb\u7edf\u63d0\u793a\u8bcd|\u89d2\u8272\u8bbe\u5b9a)"
            r"\s*(?:is|\u4e3a|\u662f|=|:)\s*([^。；;\n]+)",
        ),
    )
    purpose = _extract_named_value(
        user_request,
        (
            r"(?:purpose|\u7528\u9014|\u76ee\u6807)\s*"
            r"(?:is|\u4e3a|\u662f|=|:)\s*([^。；;\n]+)",
        ),
    )
    if not name:
        return None
    if provider_override == "builtin":
        provider = "builtin"
    elif base_agent_id:
        provider = BASE_AGENT_PROVIDERS[base_agent_id]
    else:
        return None
    role = _extract_named_value(
        user_request,
        (
            r"(?:role|\u89d2\u8272)\s*"
            r"(?:is|\u4e3a|\u662f|=|:)\s*([^。；;\n]+)",
        ),
    )
    capabilities = _extract_list_field(
        user_request,
        ("capabilities", "\u80fd\u529b\u6807\u7b7e", "\u80fd\u529b"),
    )
    preferred_task_types = _extract_list_field(
        user_request,
        (
            "preferred_task_types",
            "\u9002\u5408\u4efb\u52a1\u7c7b\u578b",
            "\u4efb\u52a1\u7c7b\u578b",
        ),
    )
    strengths = _extract_list_field(
        user_request,
        ("planning_strengths", "\u64c5\u957f\u4ec0\u4e48", "\u64c5\u957f"),
    )
    weaknesses = _extract_list_field(
        user_request,
        (
            "planning_weaknesses",
            "\u4e0d\u64c5\u957f\u4ec0\u4e48",
            "\u4e0d\u64c5\u957f",
        ),
    )
    output_style = _extract_named_value(
        user_request,
        (
            r"(?:output_style|\u8f93\u51fa\u98ce\u683c)\s*"
            r"(?:is|\u4e3a|\u662f|=|:)\s*([^。；;\n]+)",
        ),
    )
    boundaries = _extract_list_field(
        user_request,
        ("boundaries", "\u8fb9\u754c", "\u9650\u5236"),
    )

    prompt = system_prompt or role or purpose
    if not prompt:
        return None

    wrapper_profile = {
        "role": role or prompt,
        "purpose": purpose or prompt,
        "planning_profile": _extract_named_value(
            user_request,
            (
                r"(?:planning_profile|\u8c03\u5ea6\u63cf\u8ff0)\s*"
                r"(?:is|\u4e3a|\u662f|=|:)\s*([^。；;\n]+)",
            ),
        )
        or purpose
        or prompt,
        "planning_strengths": strengths,
        "planning_weaknesses": weaknesses,
        "preferred_task_types": preferred_task_types,
        "capabilities": capabilities,
        "output_style": output_style or "",
        "boundaries": boundaries,
    }

    if provider == "builtin":
        allowed_tools = _extract_list_field(
            user_request,
            ("allowed_tools", "\u5de5\u5177\u767d\u540d\u5355", "\u5de5\u5177"),
        )
        model_backend = _extract_model_backend(user_request) or "deepseek"
        return {
            "name": name,
            "provider": provider,
            "system_prompt": prompt,
            "capabilities": capabilities,
            "config": {
                "model_backend": model_backend,
                "allowed_tools": allowed_tools or [],
                "mcp_servers": [],
                "planning_profile": wrapper_profile["planning_profile"],
                "planning_strengths": strengths,
                "planning_weaknesses": weaknesses,
                "preferred_task_types": preferred_task_types,
            },
            "add_to_conversation": _should_add_to_conversation(user_request),
        }

    return {
        "name": name,
        "provider": provider,
        "system_prompt": prompt,
        "capabilities": capabilities,
        "config": {
            "custom_agent_mode": WRAPPER_MODE,
            "base_agent_id": base_agent_id,
            "wrapper_profile": wrapper_profile,
        },
        "add_to_conversation": _should_add_to_conversation(user_request),
    }


def custom_agent_result_text(status: str, output: str | None) -> str:
    payload: Mapping[str, Any] = {}
    if output:
        try:
            parsed = json.loads(output)
            if isinstance(parsed, Mapping):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    if status == "ok":
        agent = payload.get("agent")
        if isinstance(agent, Mapping):
            capabilities = ", ".join(str(item) for item in agent.get("capabilities", []))
            mode = (
                "\u81ea\u5b9a\u4e49 Agent"
                if agent.get("provider") == "builtin"
                else "\u81ea\u5b9a\u4e49 Agent \u5957\u58f3"
            )
            return (
                f"\u5df2\u521b\u5efa{mode}\uff0c"
                "\u5e76\u53ef\u52a0\u5165\u5f53\u524d\u7fa4\u804a\u3002\n"
                f"- id: {agent.get('id')}\n"
                f"- name: {agent.get('name')}\n"
                f"- provider: {agent.get('provider')}\n"
                f"- base_agent_id: {agent.get('base_agent_id')}\n"
                f"- capabilities: {capabilities}"
            )
        return "\u5df2\u521b\u5efa\u81ea\u5b9a\u4e49 Agent \u5957\u58f3\u3002"
    missing = payload.get("missing_fields")
    if isinstance(missing, list) and missing:
        prefix = "\u521b\u5efa\u81ea\u5b9a\u4e49 Agent \u8fd8\u7f3a\u5c11\u4fe1\u606f\uff1a"
        return prefix + ", ".join(str(item) for item in missing)
    error = payload.get("error") if isinstance(payload.get("error"), str) else None
    prefix = "\u521b\u5efa\u81ea\u5b9a\u4e49 Agent \u5931\u8d25\uff1a"
    return f"{prefix}{error or output or 'unknown error'}"


def _looks_like_custom_agent_request(user_request: str) -> bool:
    lowered = user_request.lower()
    return (
        ("agent" in lowered or SMART_AGENT_WORD in user_request or AGENT_WORD in user_request)
        and any(marker in user_request for marker in CREATE_WORDS)
    )


def _extract_base_agent_id(text: str) -> str | None:
    raw = _extract_named_value(
        text,
        (
            (
                r"(?:base_agent_id|base agent|\u5e95\u5ea7 Agent|\u5e95\u5ea7|"
                r"\u57fa\u4e8e|\u5957\u58f3\u81ea)\s*"
                r"(?:use|\u4f7f\u7528|\u4e3a|\u662f|=|:)?\s*"
                r"[\"'\u201c\u201d\u2018\u2019]?([A-Za-z0-9 _-]+)"
            ),
            (
                r"(?:provider|\u63d0\u4f9b\u5546|\u7c7b\u578b)\s*"
                r"(?:use|\u4f7f\u7528|\u4e3a|\u662f|=|:)\s*"
                r"[\"'\u201c\u201d\u2018\u2019]?([A-Za-z0-9 _-]+)"
            ),
        ),
    )
    if not raw:
        lowered = text.lower()
        for alias, base_agent_id in BASE_AGENT_ALIASES.items():
            if alias in lowered:
                return base_agent_id
        return None
    normalized = raw.strip().lower().replace("_", "-")
    return BASE_AGENT_ALIASES.get(normalized) or BASE_AGENT_ALIASES.get(
        normalized.replace("-", " ")
    )


def _extract_provider(text: str) -> str | None:
    raw = _extract_named_value(
        text,
        (
            (
                r"(?:provider|\u63d0\u4f9b\u5546|\u7c7b\u578b)"
                r"\s*(?:use|\u4f7f\u7528|\u4e3a|\u662f|=|:)\s*"
                r"[\"'\u201c\u201d\u2018\u2019]?([A-Za-z0-9 _-]+)"
            ),
        ),
    )
    if not raw:
        return None
    normalized = raw.strip().lower().replace("_", "-")
    return PROVIDER_ALIASES.get(normalized) or PROVIDER_ALIASES.get(
        normalized.replace("-", " ")
    )


def _extract_model_backend(text: str) -> str | None:
    raw = _extract_named_value(
        text,
        (
            (
                r"(?:model_backend|\u6a21\u578b\u540e\u7aef|\u6a21\u578b)"
                r"\s*(?:use|\u4f7f\u7528|\u8bbe\u7f6e\u4e3a|\u4e3a|\u662f|=|:)\s*"
                r"[\"'\u201c\u201d\u2018\u2019]?([A-Za-z0-9 _-]+)"
            ),
        ),
    )
    if not raw:
        return None
    normalized = raw.strip().lower().replace("_", "-")
    return MODEL_BACKEND_ALIASES.get(normalized)


def _extract_named_value(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if not match:
            continue
        value = match.group(1).strip()
        value = value.strip(" \t\r\n\"'\u201c\u201d\u2018\u2019")
        if value:
            return value
    return None


def _extract_list_field(user_request: str, names: tuple[str, ...]) -> list[str]:
    alternatives = "|".join(re.escape(name) for name in names)
    match = re.search(
        rf"(?:{alternatives})\s*(?:\u8bbe\u7f6e\u4e3a|\u4e3a|\u662f|=|:)\s*([^。；;\n]+)",
        user_request,
        re.I,
    )
    if not match:
        return []
    raw = match.group(1)
    parts = re.split(r"[,，、]\s*", raw)
    values: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = part.strip().strip("\"'\u201c\u201d\u2018\u2019")
        if any(stop in value for stop in ("\u5e76", "\u7136\u540e", "\u52a0\u5165")):
            value = re.split(
                r"\u5e76|\u7136\u540e|\u52a0\u5165",
                value,
                maxsplit=1,
            )[0].strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _should_add_to_conversation(user_request: str) -> bool:
    lowered = user_request.lower()
    if "do not add" in lowered:
        return False
    if "add" in lowered and "current group" in lowered:
        return True
    if DO_NOT_JOIN in user_request:
        return False
    return JOIN in user_request and (GROUP_CHAT in user_request or CURRENT in user_request)
