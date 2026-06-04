"""Custom-agent request routing helpers for Orchestrator."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


def custom_agent_tool_arguments(user_request: str) -> dict[str, Any] | None:
    if not _looks_like_custom_agent_request(user_request):
        return None
    name = _extract_named_value(
        user_request,
        (
            r"(?:名字|名称|name)\s*(?:为|是|叫|=|:)\s*[\"'“”‘’]?([^，,。；;\n\"'“”‘’]+)",
        ),
    )
    provider = _extract_named_value(
        user_request,
        (
            r"provider\s*(?:使用|为|是|=|:)\s*[\"'“”‘’]?([A-Za-z0-9_-]+)",
            r"(?:提供商|类型)\s*(?:使用|为|是|=|:)\s*[\"'“”‘’]?([A-Za-z0-9_-]+)",
        ),
    )
    system_prompt = _extract_named_value(
        user_request,
        (
            r"system_prompt\s*(?:为|是|=|:)\s*[\"“](.+?)[\"”]",
            r"(?:系统提示词|角色设定)\s*(?:为|是|=|:)\s*[\"“](.+?)[\"”]",
        ),
    )
    if not name or not provider or not system_prompt:
        return None

    result: dict[str, Any] = {
        "name": name,
        "provider": provider,
        "system_prompt": system_prompt,
        "capabilities": _extract_capabilities(user_request),
        "config": {},
        "add_to_conversation": _should_add_to_conversation(user_request),
    }
    allowed_tools = _extract_allowed_tools(user_request)
    if allowed_tools is not None:
        result["allowed_tools"] = allowed_tools
    return result


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
            allowed_tools = ", ".join(
                str(item) for item in agent.get("allowed_tools") or []
            )
            return (
                "已创建自建 Agent 并加入当前群聊。\n"
                f"- id: {agent.get('id')}\n"
                f"- name: {agent.get('name')}\n"
                f"- provider: {agent.get('provider')}\n"
                f"- capabilities: {capabilities}\n"
                f"- allowed_tools: {allowed_tools}"
            )
        return "已创建自建 Agent。"
    missing = payload.get("missing_fields")
    if isinstance(missing, list) and missing:
        return "创建自建 Agent 还缺少信息：" + ", ".join(str(item) for item in missing)
    error = payload.get("error") if isinstance(payload.get("error"), str) else None
    return f"创建自建 Agent 失败：{error or output or 'unknown error'}"


def _looks_like_custom_agent_request(user_request: str) -> bool:
    lowered = user_request.lower()
    return (
        ("agent" in lowered or "智能体" in user_request or "代理" in user_request)
        and any(marker in user_request for marker in ("创建", "新建", "新增", "create"))
    )


def _extract_named_value(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if not match:
            continue
        value = match.group(1).strip()
        value = value.strip(" \t\r\n\"'“”‘’")
        if value:
            return value
    return None


def _extract_capabilities(user_request: str) -> list[str]:
    match = re.search(
        r"(?:capabilities|能力标签|能力)\s*(?:设置为|为|是|=|:)\s*([^。；;\n]+)",
        user_request,
        re.I,
    )
    if not match:
        return []
    raw = match.group(1)
    parts = re.split(r"[,，、/]\s*", raw)
    capabilities: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = part.strip().strip("\"'“”‘’")
        if not value or value in seen:
            continue
        if any(stop in value for stop in ("并", "然后", "加入")):
            value = re.split(r"并|然后|加入", value, maxsplit=1)[0].strip()
        if value:
            seen.add(value)
            capabilities.append(value)
    return capabilities


def _extract_allowed_tools(user_request: str) -> list[str] | None:
    match = re.search(
        r"(?:allowed_tools|工具白名单|允许工具|工具)\s*(?:设置为|为|是|=|:)\s*([^。；;\n]+)",
        user_request,
        re.I,
    )
    if not match:
        return None
    raw = match.group(1)
    parts = re.split(r"[,，、/]\s*", raw)
    tools: list[str] = []
    for part in parts:
        value = part.strip().strip("\"'“”‘’")
        if any(stop in value for stop in ("并", "然后", "加入")):
            value = re.split(r"并|然后|加入", value, maxsplit=1)[0].strip()
        if value:
            tools.append(value)
    return tools


def _should_add_to_conversation(user_request: str) -> bool:
    if "不加入" in user_request:
        return False
    return "加入" in user_request and ("群聊" in user_request or "当前" in user_request)
