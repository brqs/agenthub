"""Tests for AgentRegistry runtime provider wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

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
from app.models.upload import Upload
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
    def __init__(
        self,
        agents: dict[str, Agent],
        uploads: dict[UUID, Upload] | None = None,
    ) -> None:
        self.agents = agents
        self.uploads = uploads or {}

    async def get(self, model: object, key: object) -> Agent | Upload | None:
        if model is Agent:
            return self.agents.get(str(key))
        if model is Upload:
            if not isinstance(key, UUID):
                return None
            return self.uploads.get(key)
        raise AssertionError(f"unexpected model: {model}")


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
        }
    )

    assert isinstance(await get_adapter("claude-code", db), ClaudeCodeAdapter)  # type: ignore[arg-type]
    assert isinstance(await get_adapter("codex-helper", db), CodexAdapter)  # type: ignore[arg-type]
    assert isinstance(await get_adapter("opencode-helper", db), OpenCodeAdapter)  # type: ignore[arg-type]


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


async def test_legacy_raw_provider_migrates_to_builtin_adapter() -> None:
    adapter = await get_adapter(
        "legacy-claude",
        FakeDb({"legacy-claude": _agent("legacy-claude", "claude", {"model": "old"})}),
    )  # type: ignore[arg-type]

    assert isinstance(adapter, BuiltinAgentAdapter)
    assert adapter.default_config["model_backend"] == "claude"


async def test_registry_injects_custom_agent_uploaded_assets(tmp_path: Path) -> None:
    upload_id = uuid4()
    owner_id = uuid4()
    knowledge_path = tmp_path / "rules.md"
    knowledge_path.write_text("# Rules\nAlways use the project vocabulary.", encoding="utf-8")
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(
        "---\nname: Review Skill\ndescription: Review markdown drafts.\n---\nUse checklist style.",
        encoding="utf-8",
    )
    skill_upload_id = uuid4()
    agent = Agent(
        id="custom-agent",
        user_id=owner_id,
        name="Custom Agent",
        provider="builtin",
        avatar_url="",
        capabilities=["review"],
        system_prompt="Base prompt.",
        config={
            "model_backend": "deepseek",
            "mcp_servers": [],
            "knowledge": [
                {
                    "upload_id": str(upload_id),
                    "label": "Rules",
                    "usage": "policy",
                }
            ],
            "skills": [
                {
                    "skill_id": "skill_1",
                    "upload_id": str(skill_upload_id),
                    "name": "Review Skill",
                    "description": "Review markdown drafts.",
                }
            ],
        },
        is_builtin=False,
    )
    db = FakeDb(
        {"custom-agent": agent},
        uploads={
            upload_id: _upload(upload_id, owner_id, "rules.md", knowledge_path),
            skill_upload_id: _upload(skill_upload_id, owner_id, "SKILL.md", skill_path),
        },
    )

    adapter = await get_adapter("custom-agent", db)  # type: ignore[arg-type]

    assert isinstance(adapter, BuiltinAgentAdapter)
    assert adapter.system_prompt is not None
    assert "Base prompt." in adapter.system_prompt
    assert "Agent Knowledge" in adapter.system_prompt
    assert "Always use the project vocabulary." in adapter.system_prompt
    assert "Agent Skills" in adapter.system_prompt
    assert "Use checklist style." in adapter.system_prompt


async def test_registry_skips_unsafe_or_cross_owner_assets(tmp_path: Path) -> None:
    owner_id = uuid4()
    blocked_id = uuid4()
    other_owner_id = uuid4()
    other_id = uuid4()
    blocked_path = tmp_path / "blocked.md"
    blocked_path.write_text("blocked content", encoding="utf-8")
    other_path = tmp_path / "other.md"
    other_path.write_text("other content", encoding="utf-8")
    agent = Agent(
        id="custom-agent",
        user_id=owner_id,
        name="Custom Agent",
        provider="builtin",
        avatar_url="",
        capabilities=["review"],
        system_prompt="Base prompt.",
        config={
            "model_backend": "deepseek",
            "mcp_servers": [],
            "knowledge": [
                {"upload_id": str(blocked_id), "label": "Blocked"},
                {"upload_id": str(other_id), "label": "Other"},
            ],
        },
        is_builtin=False,
    )
    blocked_upload = _upload(blocked_id, owner_id, "blocked.md", blocked_path)
    blocked_upload.safety_status = "blocked"
    db = FakeDb(
        {"custom-agent": agent},
        uploads={
            blocked_id: blocked_upload,
            other_id: _upload(other_id, other_owner_id, "other.md", other_path),
        },
    )

    adapter = await get_adapter("custom-agent", db)  # type: ignore[arg-type]

    assert adapter.system_prompt == "Base prompt."


def _upload(upload_id: UUID, owner_id: UUID, filename: str, path: Path) -> Upload:
    return Upload(
        id=upload_id,
        owner_user_id=owner_id,
        conversation_id=None,
        purpose="agent_knowledge",
        filename=filename,
        content_type="text/markdown",
        detected_content_type="text/markdown",
        size_bytes=path.stat().st_size,
        sha256="hash",
        storage_key=str(path),
        status="ready",
        safety_status="passed",
        preview={},
    )
