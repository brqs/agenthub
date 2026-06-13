"""Self-healing config upgrades for built-in agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config_fields import ORCHESTRATOR_DEFAULTS
from app.agents.registry import ORCHESTRATOR_AGENT_ID
from app.models.agent import Agent
from app.seeds.seed_agents import ACTIVE_BUILTIN_AGENT_IDS, BUILTIN_AGENTS

MANAGED_BUILTIN_AGENT_IDS = ACTIVE_BUILTIN_AGENT_IDS - {ORCHESTRATOR_AGENT_ID}

ORCHESTRATOR_CONFIG_UPGRADES = {
    "answer_model_backend": ORCHESTRATOR_DEFAULTS["answer_model_backend"],
    "planner_model_backend": ORCHESTRATOR_DEFAULTS["planner_model_backend"],
    "orchestrator_control_mode": ORCHESTRATOR_DEFAULTS["orchestrator_control_mode"],
    "planner_fallback_to_template": ORCHESTRATOR_DEFAULTS[
        "planner_fallback_to_template"
    ],
    "react_trace_visible": ORCHESTRATOR_DEFAULTS["react_trace_visible"],
    "available_agents_authoritative": ORCHESTRATOR_DEFAULTS[
        "available_agents_authoritative"
    ],
    "orchestrator_group_messages_enabled": ORCHESTRATOR_DEFAULTS[
        "orchestrator_group_messages_enabled"
    ],
    "orchestrator_process_block_enabled": ORCHESTRATOR_DEFAULTS[
        "orchestrator_process_block_enabled"
    ],
}
BUILTIN_AGENTS_BY_ID = {agent["id"]: agent for agent in BUILTIN_AGENTS}


def upgraded_orchestrator_config(config: object) -> dict[str, Any]:
    """Return an Orchestrator config with runtime-safe built-in defaults applied."""

    base = dict(config) if isinstance(config, Mapping) else {}
    base.update(ORCHESTRATOR_CONFIG_UPGRADES)
    base = _remove_stale_managed_agent_ids(base)
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


async def reconcile_builtin_agents(db: AsyncSession) -> bool:
    """Apply current built-in definitions and remove stale built-in rows."""

    changed = False
    existing_result = await db.execute(select(Agent).where(Agent.is_builtin.is_(True)))
    for agent in existing_result.scalars():
        seed = BUILTIN_AGENTS_BY_ID.get(agent.id)
        if seed is None:
            await db.delete(agent)
            changed = True
            continue
        config = dict(seed["config"])
        if agent.id == ORCHESTRATOR_AGENT_ID:
            config = upgraded_orchestrator_config(config)
        if (
            agent.user_id is not None
            or agent.name != seed["name"]
            or agent.provider != seed["provider"]
            or agent.avatar_url != seed["avatar_url"]
            or agent.capabilities != seed["capabilities"]
            or agent.system_prompt != seed["system_prompt"]
            or agent.config != config
        ):
            agent.user_id = None
            agent.name = seed["name"]
            agent.provider = seed["provider"]
            agent.avatar_url = seed["avatar_url"]
            agent.capabilities = seed["capabilities"]
            agent.system_prompt = seed["system_prompt"]
            agent.config = config
            changed = True

    for seed in BUILTIN_AGENTS:
        exists = await db.get(Agent, seed["id"])
        if exists is not None:
            continue
        db.add(Agent(is_builtin=True, **seed))
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
