"""Self-healing config upgrades for built-in agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config_fields import ORCHESTRATOR_DEFAULTS
from app.agents.registry import ORCHESTRATOR_AGENT_ID
from app.models.agent import Agent

ORCHESTRATOR_CONFIG_UPGRADES = {
    "answer_model_backend": ORCHESTRATOR_DEFAULTS["answer_model_backend"],
    "planner_model_backend": ORCHESTRATOR_DEFAULTS["planner_model_backend"],
    "react_trace_visible": ORCHESTRATOR_DEFAULTS["react_trace_visible"],
    "orchestrator_group_messages_enabled": ORCHESTRATOR_DEFAULTS[
        "orchestrator_group_messages_enabled"
    ],
    "orchestrator_process_block_enabled": ORCHESTRATOR_DEFAULTS[
        "orchestrator_process_block_enabled"
    ],
}


def upgraded_orchestrator_config(config: object) -> dict[str, Any]:
    """Return an Orchestrator config with runtime-safe built-in defaults applied."""

    base = dict(config) if isinstance(config, Mapping) else {}
    base.update(ORCHESTRATOR_CONFIG_UPGRADES)
    return base


async def upgrade_builtin_orchestrator_config(db: AsyncSession) -> bool:
    """Upgrade stale built-in Orchestrator config rows in existing local databases."""

    agent = await db.get(Agent, ORCHESTRATOR_AGENT_ID)
    if agent is None or not agent.is_builtin:
        return False
    upgraded = upgraded_orchestrator_config(agent.config)
    if upgraded == agent.config:
        return False
    agent.config = upgraded
    return True
