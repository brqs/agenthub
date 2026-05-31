"""
AdapterRegistry — single entry point for B1 to obtain an Adapter instance.

B1 should NEVER import a specific adapter class. Always go through `get_adapter()`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.adapters.mock import MockAdapter
from app.agents.base import BaseAgentAdapter
from app.agents.builtin.adapter import BuiltinAgentAdapter
from app.agents.config_fields import ORCHESTRATOR_DEFAULTS
from app.agents.external.claude_code import ClaudeCodeAdapter
from app.agents.external.codex import CodexAdapter
from app.agents.external.opencode import OpenCodeAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.models.agent import Agent

# provider string → adapter class
PROVIDER_MAP: dict[str, type[BaseAgentAdapter]] = {
    "mock": MockAdapter,
    "claude_code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "opencode": OpenCodeAdapter,
    "builtin": BuiltinAgentAdapter,
}

LEGACY_RAW_PROVIDER_TO_MODEL_BACKEND = {
    "claude": "claude",
    "deepseek": "deepseek",
    "openai": "openai",
    "custom": "claude",
}

ORCHESTRATOR_AGENT_ID = "orchestrator"
DEFAULT_ORCHESTRATOR_SUB_AGENT_IDS = [
    "claude-code",
    "codex-helper",
    "opencode-helper",
    "web-designer",
]


class AgentNotFoundError(Exception):
    """Raised when an agent_id has no registered adapter."""


async def get_adapter(agent_id: str, db: AsyncSession) -> BaseAgentAdapter:
    """
    Fetch the Agent row and instantiate the proper Adapter.

    Args:
        agent_id: Agent primary key (e.g., "claude-code" or a uuid).
        db: Active DB session (read-only here).

    Raises:
        AgentNotFoundError: If agent not found.
        ValueError: If provider unknown or its API key not configured.
    """
    # Dev shortcut: explicit mock
    if agent_id == "mock":
        return MockAdapter(agent_id="mock")

    agent: Agent | None = await db.get(Agent, agent_id)
    if not agent:
        raise AgentNotFoundError(f"Agent {agent_id!r} not found")

    if agent.id == ORCHESTRATOR_AGENT_ID:
        async def adapter_factory(sub_agent_id: str) -> BaseAgentAdapter:
            if sub_agent_id == ORCHESTRATOR_AGENT_ID:
                raise ValueError("orchestrator cannot dispatch to itself")
            return await get_adapter(sub_agent_id, db)

        default_config = {**ORCHESTRATOR_DEFAULTS, **dict(agent.config or {})}
        default_config.setdefault(
            "managed_agent_ids",
            DEFAULT_ORCHESTRATOR_SUB_AGENT_IDS,
        )
        default_config["adapter_factory"] = adapter_factory
        return OrchestratorAdapter(
            agent_id=agent.id,
            system_prompt=agent.system_prompt,
            default_config=default_config,
        )

    adapter_cls, default_config = _adapter_class_and_config(agent)
    return adapter_cls(
        agent_id=agent.id,
        system_prompt=agent.system_prompt,
        default_config=default_config,
    )


def _adapter_class_and_config(agent: Agent) -> tuple[type[BaseAgentAdapter], dict[str, object]]:
    adapter_cls = PROVIDER_MAP.get(agent.provider)
    if adapter_cls:
        return adapter_cls, dict(agent.config or {})

    legacy_model_backend = LEGACY_RAW_PROVIDER_TO_MODEL_BACKEND.get(agent.provider)
    if legacy_model_backend:
        return BuiltinAgentAdapter, _legacy_builtin_config(agent.provider, agent.config or {})

    raise ValueError(f"Unknown provider: {agent.provider}")


def _legacy_builtin_config(provider: str, config: dict[str, Any]) -> dict[str, object]:
    migrated = dict(config)
    migrated["model_backend"] = str(
        migrated.pop("upstream_provider", None)
        or LEGACY_RAW_PROVIDER_TO_MODEL_BACKEND[provider]
    )
    migrated.setdefault("max_iterations", 10)
    migrated.setdefault("mcp_servers", [])
    return migrated
