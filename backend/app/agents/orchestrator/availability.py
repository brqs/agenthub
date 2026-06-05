"""Helpers for filtering runnable Orchestrator conversation agents."""

from __future__ import annotations

from collections.abc import Mapping

UNRUNNABLE_RUNTIME_STATUSES = {
    "error",
    "invalid",
    "missing",
    "not_found",
    "not_installed",
    "unavailable",
}


def runnable_agent_id(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return None
    raw_id = item.get("agent_id", item.get("id"))
    if not isinstance(raw_id, str):
        return None
    agent_id = raw_id.strip()
    if not agent_id or agent_id == "orchestrator":
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
