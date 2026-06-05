"""Direct mention and broadcast routing helpers for orchestrator planning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator.availability import scoped_runnable_agent_ids
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage

TASK_INTENT_MARKERS = (
    "\u751f\u6210",
    "\u521b\u5efa",
    "\u8bbe\u8ba1",
    "\u5236\u4f5c",
    "\u5f00\u53d1",
    "\u505a\u4e00\u4e2a",
    "\u5199\u4e00\u4e2a",
    "\u5199\u5165",
    "\u5b9e\u73b0",
    "\u6784\u5efa",
    "\u4fee\u6539",
    "\u4fee\u590d",
    "\u90e8\u7f72",
    "\u53d1\u5e03",
    "\u9884\u89c8",
    "\u8fd0\u884c",
    "\u5206\u6790\u4ed3\u5e93",
    "\u8bfb\u6587\u4ef6",
    "\u5199\u6587\u4ef6",
    "\u8c03\u7528",
    "\u534f\u8c03",
    "生成",
    "创建",
    "写一个",
    "写入",
    "实现",
    "构建",
    "修改",
    "修复",
    "部署",
    "复核",
    "安排",
    "协调",
    "调用",
    "分别",
    "让 ",
    "让@",
    "build",
    "create",
    "generate",
    "design",
    "make",
    "write",
    "implement",
    "fix",
    "deploy",
    "review",
    "coordinate",
    "ask ",
)
ARTIFACT_BUILD_VERB_MARKERS = (
    "\u8bbe\u8ba1",
    "\u5236\u4f5c",
    "\u5f00\u53d1",
    "\u505a",
    "\u751f\u6210",
    "\u521b\u5efa",
    "\u5199",
    "\u5b9e\u73b0",
    "\u6784\u5efa",
    "design",
    "make",
    "build",
    "create",
    "generate",
    "write",
    "implement",
)
ARTIFACT_BUILD_NOUN_MARKERS = (
    "\u7f51\u9875",
    "\u9875\u9762",
    "\u7f51\u7ad9",
    "\u7f51\u9875\u7248",
    "\u524d\u7aef",
    "\u754c\u9762",
    "\u6e38\u620f",
    "\u7ec4\u4ef6",
    "\u4ee3\u7801",
    "\u6587\u4ef6",
    "html",
    "css",
    "javascript",
    "js",
    "frontend",
    "front-end",
    "web",
    "page",
    "site",
    "game",
    "component",
    "file",
)


def strip_orchestrator_mention(text: str) -> str:
    return text.replace("@orchestrator", "").replace("＠orchestrator", "").strip()


def has_task_intent(text: str) -> bool:
    if any(marker in text for marker in TASK_INTENT_MARKERS):
        return True
    return is_artifact_build_request(text)


def is_artifact_build_request(text: str) -> bool:
    normalized = text.lower()
    return any(marker in normalized for marker in ARTIFACT_BUILD_VERB_MARKERS) and any(
        marker in normalized for marker in ARTIFACT_BUILD_NOUN_MARKERS
    )


def agent_id_list(value: object) -> list[str]:
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


def latest_user_request(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return "Handle the user's request."


def explicit_agent_mentions(agent_ids: list[str], user_request: str) -> list[str]:
    normalized = user_request.lower()
    available = set(agent_ids)
    positions: list[tuple[int, int, str]] = []

    for order, agent_id in enumerate(agent_ids):
        if agent_id not in available:
            continue
        position = _first_alias_position(normalized, _agent_aliases(agent_id))
        if position is not None:
            positions.append((position, order, agent_id))

    positions.sort()
    return [agent_id for _, _, agent_id in positions]


def direct_tasks_from_request(
    config: Mapping[str, Any], messages: list[ChatMessage]
) -> list[SubTask]:
    scoped_ids = scoped_runnable_agent_ids(config)
    agent_ids = (
        scoped_ids
        if scoped_ids is not None
        else agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))
    )
    if not agent_ids:
        return []
    return derive_direct_agent_tasks(agent_ids, latest_user_request(messages))


def direct_answer_on_planner_failure(config: Mapping[str, Any]) -> bool:
    return config.get("direct_answer_on_planner_failure") is True


def derive_direct_agent_tasks(agent_ids: list[str], user_request: str) -> list[SubTask]:
    targets = explicit_agent_mentions(agent_ids, user_request)
    if len(targets) < 2:
        return []

    message = _direct_broadcast_message(user_request)
    if message is None:
        return []
    return [
        SubTask(
            task_id=f"direct-{index + 1}",
            agent_id=agent_id,
            title="Direct request",
            instruction=_direct_agent_instruction(message),
            priority=index,
            include_history=False,
        )
        for index, agent_id in enumerate(targets)
    ]


def _direct_broadcast_message(user_request: str) -> str | None:
    quoted = _extract_quoted_message(user_request)
    if quoted is None:
        return None
    normalized = user_request.lower()
    broadcast_markers = (
        "same message",
        "send",
        "ask",
        "发送",
        "转发",
        "同一句",
        "同一条",
        "同样的问题",
    )
    if any(marker in normalized for marker in broadcast_markers):
        return quoted
    return None


def _agent_aliases(agent_id: str) -> tuple[str, ...]:
    if agent_id == "claude-code":
        return ("@claude-code", "claude-code", "claude code", "claudecode")
    if agent_id == "codex-helper":
        return ("@codex-helper", "codex-helper", "codex helper", "codex")
    if agent_id == "opencode-helper":
        return (
            "@opencode-helper",
            "opencode-helper",
            "opencode helper",
            "open code",
            "opencode",
        )
    if agent_id == "web-designer":
        return ("@web-designer", "web-designer", "web designer")
    return (f"@{agent_id}", agent_id)


def _first_alias_position(text: str, aliases: tuple[str, ...]) -> int | None:
    positions = [text.find(alias) for alias in aliases]
    matches = [position for position in positions if position >= 0]
    return min(matches) if matches else None


def _extract_quoted_message(user_request: str) -> str | None:
    quote_pairs = (("“", "”"), ('"', '"'), ("'", "'"))
    for open_quote, close_quote in quote_pairs:
        start = user_request.find(open_quote)
        if start < 0:
            continue
        end = user_request.find(close_quote, start + 1)
        if end <= start:
            continue
        quoted = user_request[start + 1 : end].strip()
        if quoted:
            return quoted
    return None


def _direct_agent_instruction(message: str) -> str:
    return (
        "You are receiving a direct request from AgentHub Orchestrator.\n"
        "Answer the message yourself only. Do not contact, invoke, or simulate "
        "other agents, CLIs, or APIs.\n"
        "If the message asks what model or runtime you are, answer from your own "
        "runtime identity.\n\n"
        f"Message:\n{message}\n\n"
        "Keep the response concise."
    )
