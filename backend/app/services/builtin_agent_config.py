"""Self-healing config upgrades for built-in agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config_fields import ORCHESTRATOR_DEFAULTS
from app.agents.registry import ORCHESTRATOR_AGENT_ID
from app.models.agent import Agent
from app.seeds.seed_agents import ACTIVE_BUILTIN_AGENT_IDS

MANAGED_BUILTIN_AGENT_IDS = ACTIVE_BUILTIN_AGENT_IDS - {ORCHESTRATOR_AGENT_ID}

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
    base = _remove_stale_managed_agent_ids(base)
    return base


async def upgrade_builtin_orchestrator_config(db: AsyncSession) -> bool:
    """Upgrade stale built-in Orchestrator config rows in existing local databases."""

    changed = False
    agent = await db.get(Agent, ORCHESTRATOR_AGENT_ID)
    if agent is not None and agent.is_builtin:
        upgraded = upgraded_orchestrator_config(agent.config)
        if upgraded != agent.config:
            agent.config = upgraded
            changed = True

    stale_builtins = (
        await db.execute(select(Agent).where(Agent.is_builtin.is_(True)))
    ).scalars()
    for stale in stale_builtins:
        if stale.id not in ACTIVE_BUILTIN_AGENT_IDS:
            await db.delete(stale)
            changed = True

    return changed


def _remove_stale_managed_agent_ids(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("managed_agent_ids")
    if not isinstance(value, list):
        return config
    config["managed_agent_ids"] = [
        item
        for item in value
        if isinstance(item, str) and item in MANAGED_BUILTIN_AGENT_IDS
    ]
    return config
