"""Shared agent and request helpers for planning templates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.planning.routing import agent_id_list

PORT_NUMBER_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")


def available_orchestrator_agent_ids(config: Mapping[str, Any]) -> list[str]:
    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        ids: list[str] = []
        seen: set[str] = set()
        for item in available_agents:
            if not isinstance(item, Mapping):
                continue
            raw_id = item.get("agent_id", item.get("id"))
            if not isinstance(raw_id, str):
                continue
            agent_id = raw_id.strip()
            if not agent_id or agent_id == "orchestrator" or agent_id in seen:
                continue
            seen.add(agent_id)
            ids.append(agent_id)
        if ids:
            return ids
    return agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )


def preferred_agent(agent_ids: list[str], preference: tuple[str, ...]) -> str | None:
    available = set(agent_ids)
    for agent_id in preference:
        if agent_id in available:
            return agent_id
    return agent_ids[0] if agent_ids else None


def requested_port(text: str) -> int | None:
    match = PORT_NUMBER_RE.search(text)
    if match is None:
        return None
    port = int(match.group(1))
    if 1 <= port <= 65535:
        return port
    return None
