"""
AdapterRegistry — single entry point for B1 to obtain an Adapter instance.

B1 should NEVER import a specific adapter class. Always go through `get_adapter()`.
"""

from __future__ import annotations

import asyncio
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
from app.services.agent_asset_service import (
    append_agent_asset_context,
    build_agent_asset_context,
)

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
WRAPPER_MODE = "server_agent_wrapper"
DEFAULT_ORCHESTRATOR_SUB_AGENT_IDS = [
    "claude-code",
    "codex-helper",
    "opencode-helper",
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

    runtime_agent = await _runtime_agent_for_adapter(agent, db)
    runtime_config = _runtime_config(runtime_agent, agent)
    system_prompt = append_agent_asset_context(
        _append_wrapper_profile_context(
            _append_builder_profile_context(
                _combined_system_prompt(runtime_agent, agent),
                runtime_config,
            ),
            runtime_config,
        ),
        await build_agent_asset_context(db, agent),
    )

    if agent.id == ORCHESTRATOR_AGENT_ID:
        adapter_factory_lock = asyncio.Lock()

        async def adapter_factory(sub_agent_id: str) -> BaseAgentAdapter:
            if sub_agent_id == ORCHESTRATOR_AGENT_ID:
                raise ValueError("orchestrator cannot dispatch to itself")
            async with adapter_factory_lock:
                return await get_adapter(sub_agent_id, db)

        default_config = {**ORCHESTRATOR_DEFAULTS, **dict(agent.config or {})}
        default_config.setdefault(
            "managed_agent_ids",
            DEFAULT_ORCHESTRATOR_SUB_AGENT_IDS,
        )
        default_config["adapter_factory"] = adapter_factory
        return OrchestratorAdapter(
            agent_id=agent.id,
            system_prompt=system_prompt,
            default_config=default_config,
        )

    adapter_cls, default_config = _adapter_class_and_config(runtime_agent)
    default_config = {**default_config, **runtime_config}
    return adapter_cls(
        agent_id=agent.id,
        system_prompt=system_prompt,
        default_config=default_config,
    )


async def _runtime_agent_for_adapter(agent: Agent, db: AsyncSession) -> Agent:
    if (agent.config or {}).get("custom_agent_mode") != WRAPPER_MODE:
        return agent
    base_agent_id = (agent.config or {}).get("base_agent_id")
    if not isinstance(base_agent_id, str):
        raise ValueError("Server Agent wrapper is missing base_agent_id")
    base_agent = await db.get(Agent, base_agent_id)
    if base_agent is None or not base_agent.is_builtin:
        raise ValueError(f"Server Agent wrapper base not found: {base_agent_id}")
    if base_agent.provider != agent.provider:
        raise ValueError("Server Agent wrapper provider does not match base Agent")
    return base_agent


def _runtime_config(runtime_agent: Agent, agent: Agent) -> dict[str, Any]:
    if (agent.config or {}).get("custom_agent_mode") != WRAPPER_MODE:
        return dict(agent.config or {})
    merged = dict(runtime_agent.config or {})
    for key in (
        "custom_agent_mode",
        "base_agent_id",
        "wrapper_profile",
        "planning_profile",
        "planning_strengths",
        "planning_weaknesses",
        "preferred_task_types",
    ):
        if key in (agent.config or {}):
            merged[key] = (agent.config or {})[key]
    return merged


def _combined_system_prompt(runtime_agent: Agent, agent: Agent) -> str | None:
    if (agent.config or {}).get("custom_agent_mode") != WRAPPER_MODE:
        return agent.system_prompt
    parts = [
        runtime_agent.system_prompt,
        agent.system_prompt,
    ]
    text = "\n\n".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
    return text or None


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
        migrated.pop("upstream_provider", None) or LEGACY_RAW_PROVIDER_TO_MODEL_BACKEND[provider]
    )
    migrated.setdefault("max_iterations", 10)
    migrated.setdefault("mcp_servers", [])
    return migrated


def _append_builder_profile_context(
    system_prompt: str | None,
    config: dict[str, Any],
) -> str | None:
    profile = config.get("builder_profile")
    if not isinstance(profile, dict):
        return system_prompt
    lines = ["Custom Agent profile:"]
    _append_profile_line(lines, "Role", profile.get("role"))
    _append_profile_line(lines, "Purpose", profile.get("purpose"))
    _append_profile_line(lines, "Tone", profile.get("tone"))
    _append_profile_line(lines, "Clarification policy", profile.get("clarification_policy"))
    _append_profile_list(lines, "Goals", profile.get("goals"))
    _append_profile_list(lines, "Do not do", profile.get("do_not_do"))
    _append_profile_line(lines, "Output style", profile.get("output_style"))
    context = "\n".join(lines)
    base = (system_prompt or "").strip()
    return f"{base}\n\n{context}" if base else context


def _append_wrapper_profile_context(
    system_prompt: str | None,
    config: dict[str, Any],
) -> str | None:
    profile = config.get("wrapper_profile")
    if not isinstance(profile, dict):
        return system_prompt
    lines = ["Server Agent wrapper profile:"]
    _append_profile_line(lines, "Role", profile.get("role"))
    _append_profile_line(lines, "Purpose", profile.get("purpose"))
    _append_profile_line(lines, "Planning profile", profile.get("planning_profile"))
    _append_profile_list(lines, "Strengths", profile.get("planning_strengths"))
    _append_profile_list(lines, "Weaknesses", profile.get("planning_weaknesses"))
    _append_profile_list(lines, "Preferred task types", profile.get("preferred_task_types"))
    _append_profile_list(lines, "Capabilities", profile.get("capabilities"))
    _append_profile_line(lines, "Output style", profile.get("output_style"))
    _append_profile_list(lines, "Boundaries", profile.get("boundaries"))
    context = "\n".join(lines)
    base = (system_prompt or "").strip()
    return f"{base}\n\n{context}" if base else context


def _append_profile_line(lines: list[str], label: str, value: object) -> None:
    if isinstance(value, str) and value.strip():
        lines.append(f"- {label}: {value.strip()}")


def _append_profile_list(lines: list[str], label: str, value: object) -> None:
    if not isinstance(value, list):
        return
    items = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    if items:
        lines.append(f"- {label}: " + "; ".join(items[:8]))
