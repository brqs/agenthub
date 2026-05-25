"""
AdapterRegistry — single entry point for B1 to obtain an Adapter instance.

B1 should NEVER import a specific adapter class. Always go through `get_adapter()`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.adapters.claude import ClaudeAdapter
from app.agents.adapters.custom import CustomAdapter
from app.agents.adapters.deepseek import DeepSeekAdapter
from app.agents.adapters.mock import MockAdapter
from app.agents.adapters.openai import OpenAIAdapter
from app.agents.base import BaseAgentAdapter
from app.core.config import settings
from app.models.agent import Agent

# provider string → adapter class
PROVIDER_MAP: dict[str, type[BaseAgentAdapter]] = {
    "mock": MockAdapter,
    "claude": ClaudeAdapter,
    "deepseek": DeepSeekAdapter,
    "openai": OpenAIAdapter,
    "custom": CustomAdapter,
}


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
    if agent_id == "mock" or settings.environment == "test":
        return MockAdapter(agent_id="mock")

    agent: Agent | None = await db.get(Agent, agent_id)
    if not agent:
        raise AgentNotFoundError(f"Agent {agent_id!r} not found")

    adapter_cls = PROVIDER_MAP.get(agent.provider)
    if not adapter_cls:
        raise ValueError(f"Unknown provider: {agent.provider}")

    return adapter_cls(
        agent_id=agent.id,
        system_prompt=agent.system_prompt,
        default_config=agent.config,
    )
