"""Helpers for filtering runnable Orchestrator conversation agents."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass

UNRUNNABLE_RUNTIME_STATUSES = {
    "cooldown",
    "cooling_down",
    "error",
    "invalid",
    "missing",
    "not_found",
    "not_installed",
    "unavailable",
}
DEFAULT_RUNTIME_COOLDOWN_SECONDS = 30 * 60
MAX_RUNTIME_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
_RUNTIME_COOLDOWNS: dict[str, _RuntimeCooldown] = {}


@dataclass(frozen=True, slots=True)
class _RuntimeCooldown:
    expires_at: float
    reason: str


def runnable_agent_id(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return None
    raw_id = item.get("agent_id", item.get("id"))
    if not isinstance(raw_id, str):
        return None
    agent_id = raw_id.strip()
    if not agent_id or agent_id == "orchestrator":
        return None
    if runtime_cooldown_status(agent_id)[0] == "cooldown":
        return None
    if item.get("available") is False or item.get("runtime_available") is False:
        return None
    status = item.get("runtime_status")
    if isinstance(status, str) and status.strip().lower() in UNRUNNABLE_RUNTIME_STATUSES:
        return None
    return agent_id


def runnable_agent_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for item in value:
        agent_id = runnable_agent_id(item)
        if agent_id is None or agent_id in seen:
            continue
        seen.add(agent_id)
        ids.append(agent_id)
    return ids


def is_runnable_agent_context(item: object) -> bool:
    return runnable_agent_id(item) is not None


def available_agents_authoritative(config: Mapping[str, object]) -> bool:
    """Return true when available_agents should block global fallback candidates."""

    if config.get("available_agents_authoritative") is False:
        return False
    if config.get("available_agents_authoritative") is True:
        return True
    if config.get("conversation_scoped_agents") is True:
        return True
    return isinstance(config.get("available_agents"), list)


def scoped_runnable_agent_ids(config: Mapping[str, object]) -> list[str] | None:
    """Return runnable current-scope agent ids, or None when global fallback is allowed."""

    if not available_agents_authoritative(config):
        return None
    return runnable_agent_ids(config.get("available_agents"))


def runtime_cooldown_status(agent_id: str) -> tuple[str | None, str | None]:
    """Return active runtime cooldown state for an agent, pruning expired entries."""

    item = _RUNTIME_COOLDOWNS.get(agent_id)
    if item is None:
        return None, None
    if item.expires_at <= time.monotonic():
        _RUNTIME_COOLDOWNS.pop(agent_id, None)
        return None, None
    return "cooldown", item.reason


def mark_runtime_cooldown(
    agent_id: str,
    reason: str,
    *,
    ttl_seconds: int | None = None,
) -> None:
    """Temporarily remove a failing runtime from planner/fallback selection."""

    clean_agent_id = agent_id.strip()
    if not clean_agent_id or clean_agent_id == "orchestrator":
        return
    ttl = ttl_seconds if isinstance(ttl_seconds, int) and ttl_seconds > 0 else None
    ttl = min(ttl or DEFAULT_RUNTIME_COOLDOWN_SECONDS, MAX_RUNTIME_COOLDOWN_SECONDS)
    _RUNTIME_COOLDOWNS[clean_agent_id] = _RuntimeCooldown(
        expires_at=time.monotonic() + ttl,
        reason=_short_reason(reason),
    )


def clear_runtime_cooldowns(agent_id: str | None = None) -> None:
    """Test/maintenance helper for resetting runtime cooldown state."""

    if agent_id is None:
        _RUNTIME_COOLDOWNS.clear()
        return
    _RUNTIME_COOLDOWNS.pop(agent_id, None)


def runtime_cooldown_agent_ids() -> set[str]:
    """Return currently cooled-down agent ids, pruning expired entries."""

    for agent_id in list(_RUNTIME_COOLDOWNS):
        runtime_cooldown_status(agent_id)
    return set(_RUNTIME_COOLDOWNS)


def _short_reason(reason: str) -> str:
    normalized = " ".join(str(reason or "").replace("\x00", "").split())
    if not normalized:
        return "runtime unavailable"
    if len(normalized) > 240:
        return f"{normalized[:240]}..."
    return normalized
