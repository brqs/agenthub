"""Prompt helpers for external agent runtimes."""

from __future__ import annotations

from pathlib import Path

from app.agents.types import ChatMessage

CHINESE_IDENTITY_MARKERS = (
    "你是什么模型",
    "你是什麼模型",
    "你是谁",
    "你是誰",
    "你是什么agent",
    "你是什么智能体",
    "你是什么助手",
)
ENGLISH_IDENTITY_MARKERS = (
    "who are you",
    "what are you",
    "what model are you",
    "which model are you",
    "which agent are you",
)


def workspace_guard_prompt(workspace_path: Path) -> str:
    """Return runtime-agnostic workspace rules for external coding agents."""
    return "\n".join(
        [
            "AgentHub workspace rules:",
            f"- Workspace root: {workspace_path}",
            "- Treat the latest user message as the only active request. Earlier "
            "messages are context only; do not continue or resume earlier coding "
            "tasks unless the latest user message explicitly asks you to continue "
            "them.",
            "- If the latest user message asks what you are, which model or agent "
            "you are, your status, or asks for an explanation, answer directly in "
            "text and do not inspect files or call tools unless that message asks "
            "you to.",
            "- Create, edit, read, and reference project files only inside the "
            "workspace root. Prefer relative paths from the workspace root.",
            "- When the active request asks you to create or edit files, do the "
            "file work directly. Do not enter a read-only planning mode, ask for "
            "plan approval, or wait for user approval before writing the requested "
            "workspace files.",
            "- Never write to /home/user, /home/ubuntu, /tmp, parent directories, "
            "or any absolute path outside the workspace root.",
            "- Do not run, suggest, or print shell commands for foreground or "
            "background preview/deploy servers or other long-running processes.",
            "- Do not include preview/deploy server commands in your final text, "
            "even to say that you will not run them.",
            "- If the user asks to preview or deploy on a port, create the files and "
            "state that AgentHub platform preview/deploy must be started outside the "
            "agent runtime. Do not provide terminal commands for port previews.",
            "- For preview/deploy requests, do not create a Node/Express/Fastify/Koa/"
            "Next/Vite server, server.js, package.json start/dev/preview scripts, "
            "or server dependencies merely to expose a port. AgentHub platform owns "
            "the preview port.",
            "- For web apps, write the files in the workspace and tell the user which "
            "files changed; preview is handled by AgentHub Workspace.",
        ]
    )


def format_runtime_messages(
    messages: list[ChatMessage],
    *,
    include_system: bool = True,
) -> str:
    """Format conversation history so the latest user request is unambiguous."""
    latest_user_index = _latest_user_index(messages)
    previous: list[str] = []
    latest_user_request = ""

    for index, message in enumerate(messages):
        content = message.content.strip()
        if not content:
            continue
        if message.role == "system":
            if include_system:
                previous.append(f"System: {content}")
            continue
        if index == latest_user_index:
            latest_user_request = content
            continue
        previous.append(f"{message.role.title()}: {content}")

    sections: list[str] = []
    if previous:
        sections.append(
            "Previous conversation context (not the active task):\n"
            + "\n\n".join(previous)
        )
    if latest_user_request:
        sections.append(
            "Current user request (answer this now):\n" + latest_user_request
        )
    return "\n\n".join(sections)


def direct_identity_response(
    messages: list[ChatMessage],
    *,
    agent_id: str,
) -> str | None:
    """Return a direct response for identity questions that should not start tools."""
    latest = _latest_user_content(messages)
    if not latest or not _is_identity_question(latest):
        return None
    name = _agent_display_name(agent_id)
    if _looks_chinese(latest):
        return (
            f"我是 {name}，AgentHub 中的代码 Agent。"
            "这条消息是在询问身份，所以我会直接回答，不会继续之前的编码任务或调用工具。"
        )
    return (
        f"I am {name}, a coding agent in AgentHub. "
        "This message is asking for identity, so I will answer directly without "
        "continuing earlier coding tasks or calling tools."
    )


def direct_small_talk_response(
    messages: list[ChatMessage],
    *,
    agent_id: str,
) -> str | None:
    """Return a deterministic greeting response that should not start runtime."""
    latest = _latest_user_content(messages)
    if not latest or not _is_simple_greeting(latest):
        return None
    name = _agent_display_name(agent_id)
    if _looks_chinese(latest):
        return f"你好！我是 {name}，有什么我可以帮你的吗？"
    return f"Hello! I am {name}. How can I help?"


def _latest_user_index(messages: list[ChatMessage]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.role == "user" and message.content.strip():
            return index
    return None


def _latest_user_content(messages: list[ChatMessage]) -> str:
    index = _latest_user_index(messages)
    if index is None:
        return ""
    return messages[index].content.strip()


def _is_identity_question(text: str) -> bool:
    normalized = text.strip().lower()
    if any(marker in normalized for marker in ENGLISH_IDENTITY_MARKERS):
        return True
    if any(marker in text for marker in CHINESE_IDENTITY_MARKERS):
        return True
    return (
        "你" in text
        and "模型" in text
        and ("什么" in text or "什麼" in text or "哪" in text)
    )


def _is_simple_greeting(text: str) -> bool:
    compact = text.strip().strip("!！?？。,.， ")
    return compact.lower() in {
        "你好",
        "您好",
        "嗨",
        "哈喽",
        "hello",
        "hi",
        "hey",
    }


def _agent_display_name(agent_id: str) -> str:
    normalized = agent_id.lower()
    if "claude" in normalized:
        return "Claude Code"
    if "codex" in normalized:
        return "Codex Helper"
    if "opencode" in normalized:
        return "OpenCode Helper"
    return agent_id


def _looks_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
