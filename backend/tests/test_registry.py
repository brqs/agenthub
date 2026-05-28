"""Tests for AgentRegistry runtime provider wiring."""

from __future__ import annotations

from typing import Any

from app.agents.adapters.mock import MockAdapter
from app.agents.builtin.adapter import BuiltinAgentAdapter
from app.agents.external.claude_code import ClaudeCodeAdapter
from app.agents.external.codex import CodexAdapter
from app.agents.external.opencode import OpenCodeAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.registry import (
    DEFAULT_ORCHESTRATOR_SUB_AGENT_IDS,
    PROVIDER_MAP,
    get_adapter,
)
from app.models.agent import Agent
from app.seeds.seed_agents import BUILTIN_AGENTS


def _agent(agent_id: str, provider: str, config: dict[str, Any] | None = None) -> Agent:
    return Agent(
        id=agent_id,
        user_id=None,
        name=agent_id,
        provider=provider,
        avatar_url="/avatars/test.png",
        capabilities=["testing"],
        system_prompt="test prompt",
        config=config or {},
        is_builtin=True,
    )


class FakeDb:
    def __init__(self, agents: dict[str, Agent]) -> None:
        self.agents = agents

    async def get(self, model: object, key: str) -> Agent | None:
        assert model is Agent
        return self.agents.get(key)


def test_provider_map_contains_final_runtime_providers_only() -> None:
    assert PROVIDER_MAP == {
        "mock": MockAdapter,
        "claude_code": ClaudeCodeAdapter,
        "codex": CodexAdapter,
        "opencode": OpenCodeAdapter,
        "builtin": BuiltinAgentAdapter,
    }
    assert {"claude", "openai", "deepseek", "custom"}.isdisjoint(PROVIDER_MAP)


def test_orchestrator_seed_enables_direct_answer_fallback() -> None:
    orchestrator = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "orchestrator")

    assert orchestrator["config"]["direct_answer_on_planner_failure"] is True
    assert "Answer simple identity" in orchestrator["system_prompt"]


async def test_registry_returns_runtime_adapters_by_seed_id() -> None:
    db = FakeDb(
        {
            "claude-code": _agent("claude-code", "claude_code"),
            "codex-helper": _agent("codex-helper", "codex"),
            "opencode-helper": _agent("opencode-helper", "opencode"),
            "web-designer": _agent("web-designer", "builtin", {"model_backend": "claude"}),
        }
    )

    assert isinstance(await get_adapter("claude-code", db), ClaudeCodeAdapter)  # type: ignore[arg-type]
    assert isinstance(await get_adapter("codex-helper", db), CodexAdapter)  # type: ignore[arg-type]
    assert isinstance(await get_adapter("opencode-helper", db), OpenCodeAdapter)  # type: ignore[arg-type]
    assert isinstance(await get_adapter("web-designer", db), BuiltinAgentAdapter)  # type: ignore[arg-type]


async def test_orchestrator_adapter_factory_resolves_runtime_adapters() -> None:
    db = FakeDb(
        {
            "orchestrator": _agent(
                "orchestrator",
                "builtin",
                {"model_backend": "claude"},
            ),
            "claude-code": _agent("claude-code", "claude_code"),
            "codex-helper": _agent("codex-helper", "codex"),
            "opencode-helper": _agent("opencode-helper", "opencode"),
            "web-designer": _agent("web-designer", "builtin", {"model_backend": "claude"}),
        }
    )

    adapter = await get_adapter("orchestrator", db)  # type: ignore[arg-type]

    assert isinstance(adapter, OrchestratorAdapter)
    assert adapter.default_config["managed_agent_ids"] == DEFAULT_ORCHESTRATOR_SUB_AGENT_IDS
    adapter_factory = adapter.default_config["adapter_factory"]
    assert callable(adapter_factory)
    assert isinstance(await adapter_factory("claude-code"), ClaudeCodeAdapter)
    assert isinstance(await adapter_factory("codex-helper"), CodexAdapter)
    assert isinstance(await adapter_factory("opencode-helper"), OpenCodeAdapter)
    assert isinstance(await adapter_factory("web-designer"), BuiltinAgentAdapter)


async def test_legacy_raw_provider_migrates_to_builtin_adapter() -> None:
    adapter = await get_adapter(
        "legacy-claude",
        FakeDb({"legacy-claude": _agent("legacy-claude", "claude", {"model": "old"})}),
    )  # type: ignore[arg-type]

    assert isinstance(adapter, BuiltinAgentAdapter)
    assert adapter.default_config["model_backend"] == "claude"
