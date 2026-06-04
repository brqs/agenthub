"""Shared platform-fact data access."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def conversation_agents(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = config.get("conversation_agents")
    if not isinstance(value, list):
        return []
    agents: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        agent_id = item.get("id")
        name = item.get("name")
        if not isinstance(agent_id, str) or not agent_id.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        agents.append(item)
    return agents
