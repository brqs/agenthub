"""Per-message external runtime isolation helpers."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

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

logger = logging.getLogger(__name__)


def runtime_context_value(config: dict[str, Any] | None, key: str) -> str:
    context = (config or {}).get("runtime_context")
    if not isinstance(context, dict):
        return ""
    value = context.get(key)
    return value if isinstance(value, str) else ""


def isolated_session_id(config: dict[str, Any] | None, fallback: str) -> str:
    message_id = runtime_context_value(config, "agent_message_id")
    task_id = runtime_context_value(config, "orchestrator_task_id")
    attempt_index = runtime_context_value(config, "orchestrator_attempt_index")
    agent_id = runtime_context_value(config, "agent_id")
    if task_id or attempt_index:
        return str(
            uuid5(
                NAMESPACE_URL,
                "agenthub-runtime:"
                f"{fallback}:{message_id or fallback}:"
                f"{agent_id}:{task_id}:{attempt_index}",
            )
        )
    if message_id:
        try:
            return str(UUID(message_id))
        except ValueError:
            pass
    return str(uuid5(NAMESPACE_URL, f"agenthub-runtime:{fallback}:{message_id or fallback}"))


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
    task_id = runtime_context_value(config, "orchestrator_task_id")
    attempt_index = runtime_context_value(config, "orchestrator_attempt_index")
    base = Path(settings.external_runtime_state_dir).expanduser()
    runtime_home = (
        base
        / _safe_segment(conversation_id)
        / _safe_segment(agent_id)
        / _safe_segment(message_id)
    )
    if task_id or attempt_index:
        runtime_home = (
            runtime_home
            / _safe_segment(task_id or "unknown-task")
            / _safe_segment(attempt_index or "unknown-attempt")
        )
    return runtime_home


def _initialize_runtime_home(home: Path) -> None:
    runtime_dirs = (
        home,
        home / ".claude",
        home / ".config",
        home / ".cache",
        home / ".local",
        home / ".local" / "share",
    )
    for path in runtime_dirs:
        path.mkdir(parents=True, exist_ok=True)
    for path in runtime_dirs:
        _chmod_owner_only(path, 0o700)
    _copy_claude_credentials(home)
    claude_json = home / ".claude.json"
    if not claude_json.exists():
        claude_json.write_text(
            json.dumps({"hasCompletedOnboarding": True}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        _chmod_owner_only(claude_json, 0o600)


def _copy_claude_credentials(home: Path) -> None:
    source_home = Path(os.environ.get("HOME", "")).expanduser()
    if not source_home or source_home == home:
        return
    _copy_file_if_present(source_home / ".claude.json", home / ".claude.json")
    for filename in ("settings.json", "settings.local.json"):
        _copy_file_if_present(source_home / ".claude" / filename, home / ".claude" / filename)


def _copy_file_if_present(source: Path, target: Path) -> None:
    try:
        if not source.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        _chmod_owner_only(target, 0o600)
    except OSError:
        return


def _chmod_owner_only(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError as exc:
        logger.debug("Failed to chmod runtime isolation path %s: %s", path, exc)


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return cleaned[:120] or "unknown"
