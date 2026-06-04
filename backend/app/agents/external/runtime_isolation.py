"""Per-message external runtime isolation helpers."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.agents.external.cli_runtime import cli_env
from app.core.config import settings

PROVIDER_ENV_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_",
    "CODEX_",
    "DEEPSEEK_",
    "OPENAI_",
    "OPENCODE_",
)
PROVIDER_ENV_NAMES = {
    "API_TIMEOUT_MS",
    "ENABLE_TOOL_SEARCH",
}


def runtime_context_value(config: dict[str, Any] | None, key: str) -> str:
    context = (config or {}).get("runtime_context")
    if not isinstance(context, dict):
        return ""
    value = context.get(key)
    return value if isinstance(value, str) else ""


def isolated_session_id(config: dict[str, Any] | None, fallback: str) -> str:
    message_id = runtime_context_value(config, "agent_message_id")
    return f"agenthub-{_safe_segment(message_id or fallback)}"


def isolated_runtime_env(
    config: dict[str, Any] | None,
    *,
    workspace_path: Path,
    agent_id: str,
) -> dict[str, str]:
    """Build an env with shared secrets but isolated runtime state directories."""
    env = cli_env()
    for key, value in os.environ.items():
        if key in PROVIDER_ENV_NAMES or key.startswith(PROVIDER_ENV_PREFIXES):
            env[key] = value

    home = isolated_runtime_home(config, workspace_path=workspace_path, agent_id=agent_id)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    _initialize_runtime_home(home)
    return env


def isolated_runtime_home(
    config: dict[str, Any] | None,
    *,
    workspace_path: Path,
    agent_id: str,
) -> Path:
    conversation_id = runtime_context_value(config, "conversation_id") or workspace_path.name
    message_id = runtime_context_value(config, "agent_message_id") or "unknown-message"
    base = Path(settings.external_runtime_state_dir).expanduser()
    return (
        base
        / _safe_segment(conversation_id)
        / _safe_segment(agent_id)
        / _safe_segment(message_id)
    )


def _initialize_runtime_home(home: Path) -> None:
    for path in (
        home,
        home / ".claude",
        home / ".config",
        home / ".cache",
        home / ".local" / "share",
    ):
        path.mkdir(parents=True, exist_ok=True)
    claude_json = home / ".claude.json"
    if not claude_json.exists():
        claude_json.write_text(
            json.dumps({"hasCompletedOnboarding": True}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return cleaned[:120] or "unknown"
