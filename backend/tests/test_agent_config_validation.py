"""Tests for agent config validation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.agents.config_fields import (
    EXTERNAL_DIRECT_CHAT_DEFAULTS,
    NUMERIC_CONFIG_FIELDS,
    ORCHESTRATOR_DEFAULTS,
)
from app.agents.config_validation import (
    AgentConfigValidationError,
    merge_agent_config,
    validate_agent_config,
)
from app.api.v1.stream_orchestrator_context import _agent_context
from app.models.agent import Agent
from app.schemas.agent import AgentConfig, AgentOut, CreateAgentRequest
from app.seeds.seed_agents import BUILTIN_AGENTS
from app.services.builtin_agent_config import (
    reconcile_builtin_agents,
    upgraded_orchestrator_config,
)


class FakeUpgradeDb:
    def __init__(self, agents: dict[str, Agent]) -> None:
        self.agents = agents
        self.deleted: list[str] = []

    async def get(self, model: object, key: str) -> Agent | None:
        assert model is Agent
        return self.agents.get(key)

    async def execute(self, _statement: object) -> FakeUpgradeResult:
        return FakeUpgradeResult(
            [agent for agent in self.agents.values() if agent.is_builtin]
        )

    async def delete(self, agent: Agent) -> None:
        self.deleted.append(agent.id)
        self.agents.pop(agent.id, None)


class FakeUpgradeResult:
    def __init__(self, agents: list[Agent]) -> None:
        self._agents = agents

    def scalars(self) -> list[Agent]:
        return self._agents


def _builtin_agent_row(agent_id: str, config: dict[str, object] | None = None) -> Agent:
    return Agent(
        id=agent_id,
        user_id=None,
        name=agent_id,
        provider="builtin",
        avatar_url="",
        capabilities=[],
        system_prompt=None,
        config=config or {},
        is_builtin=True,
    )


class TestValidConfigs:
    def test_valid_claude_code_config(self) -> None:
        config = {
            "sdk_options": {},
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 180,
            "heartbeat_interval_seconds": 15,
            "context_max_tokens": 64000,
            "qa_short_circuit_enabled": True,
            "qa_model_backend": "openai",
            "qa_max_tokens": 8192,
            "qa_classifier_max_tokens": 128,
            "qa_temperature": 0.2,
            "qa_request_timeout_seconds": 20,
            "qa_stream_idle_timeout_seconds": 10,
            "qa_stream_max_runtime_seconds": 45,
            "qa_stream_heartbeat_seconds": 5,
        }
        result = validate_agent_config(
            provider="claude_code",
            config=config,
            system_prompt=None,
        )
        assert result == config

    def test_valid_codex_config(self) -> None:
        config = {
            "model": "gpt-4.1",
            "runtime": "cli",
            "sandbox_mode": "danger-full-access",
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 240,
            "heartbeat_interval_seconds": 15,
            "context_max_tokens": 64000,
        }
        result = validate_agent_config(
            provider="codex",
            config=config,
            system_prompt=None,
        )
        assert result["model"] == "gpt-4.1"
        assert result["runtime"] == "cli"
        assert result["sandbox_mode"] == "danger-full-access"
        assert result["max_runtime_seconds"] == 600
        assert result["idle_timeout_seconds"] == 240
        assert result["heartbeat_interval_seconds"] == 15

    def test_valid_opencode_config(self) -> None:
        config = {
            "command": "opencode",
            "args": ["run", "--jsonl"],
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 180,
            "heartbeat_interval_seconds": 15,
            "context_max_tokens": 64000,
        }
        result = validate_agent_config(
            provider="opencode",
            config=config,
            system_prompt=None,
        )
        assert result["command"] == "opencode"
        assert result["args"] == ["run", "--jsonl"]

    def test_valid_builtin_config(self) -> None:
        config = {
            "model_backend": "claude",
            "answer_model_backend": "openai",
            "planner_model_backend": "openai",
            "dialogue_model_backend": "openai",
            "context_max_tokens": 64000,
            "orchestrator_context_max_tokens": 64000,
            "orchestrator_subagent_context_max_tokens": 64000,
            "planner_context_max_tokens": 128000,
            "orchestrator_control_mode": "llm_first",
            "llm_planning": True,
            "orchestrator_dialogue_llm_control_enabled": True,
            "planner_fallback_to_template": False,
            "orchestrator_llm_config": {"max_tokens": 1024},
            "max_iterations": 10,
            "react_enabled": True,
            "react_trace_visible": False,
            "react_decision_max_tokens": 2048,
            "mcp_servers": [],
            "allowed_tools": ["read_file", "write_file"],
            "task_fallback_agent_ids": ["codex-helper"],
            "max_task_attempts": 2,
            "task_result_context_max_chars": 24000,
            "task_result_item_max_chars": 6000,
            "orchestrator_memory_enabled": True,
            "orchestrator_memory_recent_runs": 3,
            "orchestrator_memory_context_max_chars": 24000,
            "orchestrator_tool_calling_enabled": False,
            "orchestrator_tool_trace_visible": True,
            "orchestrator_tool_max_iterations": 12,
            "orchestrator_tool_max_tokens": 8192,
            "orchestrator_tool_result_max_chars": 12000,
            "orchestrator_tool_read_max_bytes": 262144,
            "orchestrator_group_messages_enabled": True,
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_model_backend": "deepseek",
            "orchestrator_response_polish_max_tokens": 2048,
            "orchestrator_parallel_enabled": True,
            "orchestrator_parallel_max_concurrency": 3,
            "orchestrator_evaluation_enabled": True,
            "orchestrator_evaluation_read_max_bytes": 262144,
            "orchestrator_test_runner_enabled": False,
            "orchestrator_test_command_allowlist": ["python_compile_artifacts"],
        }
        result = validate_agent_config(
            provider="builtin",
            config=config,
            system_prompt=None,
        )
        assert result == config

    def test_stale_builtin_orchestrator_config_is_upgraded(self) -> None:
        result = upgraded_orchestrator_config(
            {
                "model_backend": "claude",
                "answer_model_backend": "claude",
                "planner_model_backend": "claude",
                "react_trace_visible": True,
                "managed_agent_ids": [
                    "claude-code",
                    "codex-helper",
                    "web-designer",
                    "writer",
                    "deepseek-assistant",
                    "browser-validator",
                    "testdbg-3089345d",
                    "opencode-helper",
                ],
            }
        )

        assert result["answer_model_backend"] == "openai"
        assert result["planner_model_backend"] == "openai"
        assert result["orchestrator_control_mode"] == "llm_first"
        assert result["planner_fallback_to_template"] is False
        assert result["react_trace_visible"] is False
        assert result["managed_agent_ids"] == [
            "claude-code",
            "codex-helper",
            "opencode-helper",
        ]

    async def test_stale_builtin_agents_are_removed_during_upgrade(self) -> None:
        orchestrator = _builtin_agent_row(
            "orchestrator",
            {
                "model_backend": "claude",
                "managed_agent_ids": [
                    "claude-code",
                    "codex-helper",
                    "web-designer",
                    "writer",
                    "deepseek-assistant",
                    "browser-validator",
                    "testdbg-3089345d",
                    "opencode-helper",
                ],
            },
        )
        user_agent_named_writer = _builtin_agent_row("custom-writer")
        user_agent_named_writer.is_builtin = False
        db = FakeUpgradeDb(
            {
                "orchestrator": orchestrator,
                "claude-code": _builtin_agent_row("claude-code"),
                "codex-helper": _builtin_agent_row("codex-helper"),
                "opencode-helper": _builtin_agent_row("opencode-helper"),
                "writer": _builtin_agent_row("writer"),
                "web-designer": _builtin_agent_row("web-designer"),
                "deepseek-assistant": _builtin_agent_row("deepseek-assistant"),
                "browser-validator": _builtin_agent_row("browser-validator"),
                "testdbg-3089345d": _builtin_agent_row("testdbg-3089345d"),
                "custom-writer": user_agent_named_writer,
            }
        )

        changed = await reconcile_builtin_agents(db)  # type: ignore[arg-type]

        assert changed is True
        assert sorted(db.deleted) == [
            "browser-validator",
            "deepseek-assistant",
            "testdbg-3089345d",
            "web-designer",
            "writer",
        ]
        for agent_id in db.deleted:
            assert agent_id not in db.agents
        assert "claude-code" in db.agents
        assert "codex-helper" in db.agents
        assert "opencode-helper" in db.agents
        assert "custom-writer" in db.agents
        assert orchestrator.config["managed_agent_ids"] == [
            "claude-code",
            "codex-helper",
            "opencode-helper",
        ]

    def test_agent_context_exposes_only_safe_planning_profile_fields(self) -> None:
        agent = Agent(
            id="custom-reviewer",
            user_id=None,
            name="Custom Reviewer",
            provider="custom",
            avatar_url="",
            capabilities=["review", "frontend"],
            system_prompt="你负责审查前端交互、视觉一致性和可演示性。",
            config={
                "planning_profile": "适合作为最终审阅 agent。",
                "planning_strengths": ["ui_review", "verification"],
                "planning_weaknesses": ["backend"],
                "preferred_task_types": ["review"],
                "allowed_tools": ["read_file"],
                "model_backend": "claude",
                "api_key": "should-not-leak",
                "env": {"TOKEN": "hidden"},
                "command": "secret-command",
                "args": ["--secret"],
                "sdk_options": {"token": "hidden"},
            },
            is_builtin=False,
        )

        context = _agent_context(agent)

        assert context["planning_profile"] == "适合作为最终审阅 agent。"
        assert context["planning_strengths"] == ["ui_review", "verification"]
        assert context["planning_weaknesses"] == ["backend"]
        assert context["preferred_task_types"] == ["review"]
        assert context["allowed_tools"] == ["read_file"]
        assert "system_prompt_summary" not in context
        assert context["model_backend"] == "claude"
        assert "api_key" not in context
        assert "env" not in context
        assert "command" not in context
        assert "args" not in context
        assert "sdk_options" not in context

    def test_agent_context_uses_system_prompt_summary_without_profile(self) -> None:
        agent = Agent(
            id="custom-reviewer",
            user_id=None,
            name="Custom Reviewer",
            provider="custom",
            avatar_url="",
            capabilities=["review", "frontend"],
            system_prompt="你负责审查前端交互、视觉一致性和可演示性。",
            config={"model_backend": "claude"},
            is_builtin=False,
        )

        context = _agent_context(agent)

        assert context["system_prompt_summary"] == "你负责审查前端交互、视觉一致性和可演示性。"
        assert context["model_backend"] == "claude"

    def test_valid_builtin_mcp_allowed_tool(self) -> None:
        config = {
            "model_backend": "claude",
            "mcp_servers": [
                {"name": "fs", "command": "agenthub-fs", "args": []},
            ],
            "allowed_tools": ["mcp_fs__list_directory"],
        }
        result = validate_agent_config(
            provider="builtin",
            config=config,
            system_prompt=None,
        )
        assert result == config

    def test_valid_builtin_no_code_builder_config(self) -> None:
        config = {
            "model_backend": "deepseek",
            "max_iterations": 10,
            "mcp_servers": [],
            "allowed_tools": ["read_file", "write_file", "bash"],
            "builder_profile": {
                "role": "Frontend design assistant",
                "purpose": "Help non-technical users shape and build web pages.",
                "goals": ["Ask about missing constraints", "Produce workspace files"],
                "tone": "clear and patient",
                "do_not_do": ["Do not deploy without confirmation"],
                "clarification_policy": "balanced",
                "output_style": "Short progress notes and concrete files",
                "starters": ["Make this page more polished"],
            },
            "permissions": {
                "workspace_read": True,
                "workspace_write": True,
                "run_commands": "ask",
                "network": "never",
                "deploy": "ask",
                "external_accounts": "never",
            },
            "memory_policy": "conversation",
        }

        result = validate_agent_config(
            provider="builtin",
            config=config,
            system_prompt=None,
        )

        assert result == config

    def test_valid_server_agent_wrapper_config(self) -> None:
        config = {
            "custom_agent_mode": "server_agent_wrapper",
            "base_agent_id": "opencode-helper",
            "wrapper_profile": {
                "role": "Frontend implementer",
                "purpose": "Build static web artifacts.",
                "planning_profile": "Use for HTML/CSS/JS implementation tasks.",
                "planning_strengths": ["implementation", "verification"],
                "planning_weaknesses": ["product strategy"],
                "preferred_task_types": ["implementation"],
                "capabilities": ["frontend", "static_site"],
                "output_style": "Summarize changed files.",
                "boundaries": ["Do not deploy without confirmation"],
            },
        }

        result = validate_agent_config(
            provider="opencode",
            config=config,
            system_prompt=None,
        )

        assert result == config

    def test_server_agent_wrapper_requires_matching_base_provider(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="codex",
                config={
                    "custom_agent_mode": "server_agent_wrapper",
                    "base_agent_id": "opencode-helper",
                    "wrapper_profile": {"purpose": "Build web pages"},
                },
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "does not match the selected provider" in exc_info.value.message

    def test_server_agent_wrapper_requires_profile(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="opencode",
                config={
                    "custom_agent_mode": "server_agent_wrapper",
                    "base_agent_id": "opencode-helper",
                },
                system_prompt=None,
        )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "'wrapper_profile' must be an object" in exc_info.value.message


class TestLegacyProviderRules:
    @pytest.mark.parametrize("provider", ["claude", "openai", "deepseek", "custom"])
    def test_legacy_raw_provider_rejected_for_top_level_agent(self, provider: str) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider=provider,
                config={"model": "claude-sonnet-4-6", "upstream_provider": "claude"},
                system_prompt="legacy prompt",
            )
        assert exc_info.value.code == "INVALID_PROVIDER"


class TestModelValidation:
    def test_invalid_builtin_model_backend_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"model_backend": "custom"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL_BACKEND"

    def test_inline_api_key_rejected_for_agent_config(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={
                    "model_backend": "deepseek",
                    "api_key": "sk-should-not-be-here",
                },
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "inline API keys" in exc_info.value.message

    def test_invalid_opencode_args_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="opencode",
                config={"args": "run"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_invalid_codex_runtime_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="codex",
                config={"runtime": "browser"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_invalid_codex_sandbox_mode_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="codex",
                config={"sandbox_mode": "host"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_invalid_mcp_servers_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"mcp_servers": ["fs"]},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    @pytest.mark.parametrize(
        ("allowed_tools", "expected_message"),
        [
            ("read_file", "'allowed_tools' must be a list of strings"),
            (["read_file", ""], "entries must be non-empty"),
            (["read_file", "read_file"], "entries must be unique"),
            (["delete_file"], "builtin native tools or configured MCP tools"),
            (["mcp_fs__list_directory"], "builtin native tools or configured MCP tools"),
            (["mcp_bad"], "builtin native tools or configured MCP tools"),
        ],
    )
    def test_invalid_allowed_tools_rejected(
        self,
        allowed_tools: object,
        expected_message: str,
    ) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"mcp_servers": [], "allowed_tools": allowed_tools},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert expected_message in exc_info.value.message

    @pytest.mark.parametrize(
        ("config", "expected_message"),
        [
            (
                {"builder_profile": "reviewer"},
                "'builder_profile' must be an object",
            ),
            (
                {"builder_profile": {"goals": "ship it"}},
                "'builder_profile.goals' must be a list of strings",
            ),
            (
                {"builder_profile": {"clarification_policy": "always_execute"}},
                "'builder_profile.clarification_policy' is not supported",
            ),
            (
                {"permissions": {"workspace_write": "yes"}},
                "'permissions.workspace_write' must be a boolean",
            ),
            (
                {"permissions": {"run_commands": "always"}},
                "'permissions.run_commands' is not supported",
            ),
            (
                {"permissions": {"network": "open"}},
                "'permissions.network' is not supported",
            ),
            (
                {"permissions": {"deploy": "auto"}},
                "'permissions.deploy' is not supported",
            ),
            (
                {"memory_policy": "forever"},
                "'memory_policy' is not supported",
            ),
        ],
    )
    def test_invalid_no_code_builder_config_rejected(
        self,
        config: dict[str, object],
        expected_message: str,
    ) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config=config,
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert expected_message in exc_info.value.message


class TestNumericValidation:
    def test_timeout_one_is_allowed(self) -> None:
        config = {"timeout_seconds": 1}
        result = validate_agent_config(
            provider="codex",
            config=config,
            system_prompt=None,
        )
        assert result["timeout_seconds"] == 1

    def test_timeout_out_of_range_rejected_negative(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="codex",
                config={"timeout_seconds": -0.1},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_timeout_out_of_range_rejected_over(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="opencode",
                config={"timeout_seconds": 4000},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_max_iterations_out_of_range_rejected_zero(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"max_iterations": 0},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_max_iterations_out_of_range_rejected_large(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"max_iterations": 100},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_max_iterations_float_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"max_iterations": 1.5},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "integer" in exc_info.value.message

    def test_invalid_react_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"react_enabled": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_react_trace_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"react_trace_visible": 1},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_react_decision_max_tokens_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"react_decision_max_tokens": 4097},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "react_decision_max_tokens" in exc_info.value.message

    def test_invalid_llm_planning_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"llm_planning": "true"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "llm_planning" in exc_info.value.message

    def test_invalid_available_agents_authoritative_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"available_agents_authoritative": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "available_agents_authoritative" in exc_info.value.message

    def test_invalid_planner_model_backend_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"planner_model_backend": "local"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL_BACKEND"

    def test_invalid_response_polish_model_backend_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_response_polish_model_backend": "local"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL_BACKEND"

    def test_invalid_response_polish_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_response_polish_enabled": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_response_polish_enabled" in exc_info.value.message

    def test_invalid_orchestrator_llm_config_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_llm_config": "fast"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_timeout_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude_code",
                config={"timeout_seconds": True},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_qa_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude_code",
                config={"qa_short_circuit_enabled": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_qa_backend_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="codex",
                config={"qa_model_backend": "custom"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL_BACKEND"

    def test_invalid_qa_token_range_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="opencode",
                config={"qa_classifier_max_tokens": 2048},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "qa_classifier_max_tokens" in exc_info.value.message

    def test_invalid_qa_request_timeout_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="opencode",
                config={"qa_request_timeout_seconds": 121},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "qa_request_timeout_seconds" in exc_info.value.message

    def test_idle_timeout_cannot_exceed_max_runtime(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="opencode",
                config={"max_runtime_seconds": 10, "idle_timeout_seconds": 11},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "idle_timeout_seconds" in exc_info.value.message

    def test_max_iterations_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"max_iterations": False},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_task_fallback_agent_ids_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"task_fallback_agent_ids": "codex-helper"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "task_fallback_agent_ids" in exc_info.value.message

    def test_invalid_max_task_attempts_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"max_task_attempts": 4},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "max_task_attempts" in exc_info.value.message

    def test_invalid_task_result_context_budget_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"task_result_context_max_chars": 0},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "task_result_context_max_chars" in exc_info.value.message

    def test_invalid_context_token_budget_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude_code",
                config={"context_max_tokens": 200001},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "context_max_tokens" in exc_info.value.message

    def test_invalid_orchestrator_subagent_context_budget_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_subagent_context_max_tokens": 0},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_subagent_context_max_tokens" in exc_info.value.message

    def test_invalid_planner_context_budget_rejected(self) -> None:
        for value in (0, 1000001):
            with pytest.raises(AgentConfigValidationError) as exc_info:
                validate_agent_config(
                    provider="builtin",
                    config={"planner_context_max_tokens": value},
                    system_prompt=None,
                )
            assert exc_info.value.code == "INVALID_AGENT_CONFIG"
            assert "planner_context_max_tokens" in exc_info.value.message

    def test_invalid_orchestrator_control_mode_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_control_mode": "template_first"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_control_mode" in exc_info.value.message

    def test_invalid_dialogue_model_backend_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"dialogue_model_backend": "local"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL_BACKEND"
        assert "dialogue_model_backend" in exc_info.value.message

    def test_invalid_dialogue_llm_control_flag_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_dialogue_llm_control_enabled": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_orchestrator_memory_enabled_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_memory_enabled": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_orchestrator_memory_recent_runs_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_memory_recent_runs": 11},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_memory_recent_runs" in exc_info.value.message

    def test_invalid_orchestrator_memory_context_budget_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_memory_context_max_chars": 0},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_memory_context_max_chars" in exc_info.value.message

    def test_invalid_orchestrator_tool_calling_enabled_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_tool_calling_enabled": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_orchestrator_tool_max_iterations_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_tool_max_iterations": 51},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_tool_max_iterations" in exc_info.value.message

    def test_invalid_orchestrator_tool_max_tokens_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_tool_max_tokens": 32001},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_tool_max_tokens" in exc_info.value.message

    def test_invalid_orchestrator_tool_read_budget_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_tool_read_max_bytes": 0},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_tool_read_max_bytes" in exc_info.value.message

    def test_invalid_orchestrator_group_messages_enabled_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_group_messages_enabled": "yes"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_orchestrator_parallel_enabled_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_parallel_enabled": "yes"},
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_orchestrator_parallel_concurrency_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_parallel_max_concurrency": 0},
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_parallel_max_concurrency" in exc_info.value.message

    def test_invalid_orchestrator_evaluation_enabled_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_evaluation_enabled": "yes"},
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_orchestrator_evaluation_read_budget_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_evaluation_read_max_bytes": 0},
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_evaluation_read_max_bytes" in exc_info.value.message

    def test_invalid_orchestrator_test_runner_enabled_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_test_runner_enabled": "yes"},
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_invalid_orchestrator_test_allowlist_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"orchestrator_test_command_allowlist": "pytest"},
                system_prompt=None,
            )

        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "orchestrator_test_command_allowlist" in exc_info.value.message


class TestImmutability:
    def test_validation_does_not_mutate_input_config(self) -> None:
        original = {"model_backend": "claude", "max_iterations": 10}
        config_copy = dict(original)
        validate_agent_config(
            provider="builtin",
            config=config_copy,
            system_prompt=None,
        )
        assert config_copy == original


class TestConfigType:
    def test_config_none_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config=None,  # type: ignore[arg-type]
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "object" in exc_info.value.message


class TestMergeAgentConfig:
    def test_merge_agent_config_preserves_existing_model(self) -> None:
        existing = {"model_backend": "claude", "max_iterations": 10}
        patch = {"max_iterations": 5}
        merged = merge_agent_config(existing, patch)
        assert merged["model_backend"] == "claude"
        assert merged["max_iterations"] == 5


class TestBuiltinAgents:
    def test_builtin_agents_are_curated_runtime_set(self) -> None:
        assert {agent["id"] for agent in BUILTIN_AGENTS} == {
            "orchestrator",
            "claude-code",
            "codex-helper",
            "opencode-helper",
        }

    def test_builtin_agents_pass_validation(self) -> None:
        for agent in BUILTIN_AGENTS:
            result = validate_agent_config(
                provider=agent["provider"],
                config=agent["config"],
                system_prompt=agent["system_prompt"],
            )
            assert isinstance(result, dict)

    def test_seed_codex_uses_cli_default_model(self) -> None:
        codex_agent = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "codex-helper")

        assert "model" not in codex_agent["config"]

    def test_external_seed_agents_enable_direct_chat_defaults(self) -> None:
        for agent_id in ("claude-code", "codex-helper", "opencode-helper"):
            agent = next(agent for agent in BUILTIN_AGENTS if agent["id"] == agent_id)
            config = agent["config"]

            for key, value in EXTERNAL_DIRECT_CHAT_DEFAULTS.items():
                assert config[key] == value

    def test_seed_orchestrator_enables_react_defaults(self) -> None:
        orchestrator = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "orchestrator")
        config = orchestrator["config"]

        for key, value in ORCHESTRATOR_DEFAULTS.items():
            assert config[key] == value
        assert config["llm_planning"] is True
        assert config["orchestrator_control_mode"] == "llm_first"
        assert config["planner_fallback_to_template"] is False
        assert config["react_trace_visible"] is False
        assert config["available_agents_authoritative"] is False
        assert config["orchestrator_response_polish_enabled"] is True
        assert config["managed_agent_ids"] == [
            "claude-code",
            "codex-helper",
            "opencode-helper",
        ]

    def test_external_seed_agents_define_planning_profiles(self) -> None:
        codex = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "codex-helper")
        claude = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "claude-code")
        opencode = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "opencode-helper")

        assert "总体规划" in codex["config"]["planning_profile"]
        assert "审阅其他 agent" in codex["config"]["planning_profile"]
        assert "difficult_bug_fixing" in codex["config"]["planning_strengths"]
        assert "routine_parallel_implementation" in codex["config"]["planning_weaknesses"]
        assert "escalation" in codex["config"]["preferred_task_types"]

        assert "并行开发场景" in claude["config"]["planning_profile"]
        assert "code_review" in claude["config"]["planning_strengths"]
        assert "implementation" in claude["config"]["preferred_task_types"]

        assert "并行开发场景" in opencode["config"]["planning_profile"]
        assert "parallel_execution" in opencode["config"]["planning_strengths"]
        assert "verification" in opencode["config"]["preferred_task_types"]

    def test_external_runtime_prompts_prevent_foreground_servers(self) -> None:
        for agent_id in ("claude-code", "codex-helper", "opencode-helper"):
            agent = next(agent for agent in BUILTIN_AGENTS if agent["id"] == agent_id)
            prompt = agent["system_prompt"]

            assert "Work only inside the AgentHub workspace" in prompt
            assert "Treat the latest user message as the only active request" in prompt
            assert "answer directly in text without inspecting files or calling tools" in prompt
            assert "Do not run, suggest, or output shell commands" in prompt
            assert "Do not provide terminal commands for port previews" in prompt
            assert "platform preview/deploy must be started outside the agent runtime" in prompt
            assert "Do not create server.js" in prompt
            assert "package.json start/dev/preview scripts" in prompt
            assert "python3 -m http.server 8082" not in prompt
            assert "npm run dev" not in prompt
            assert "pnpm dev" not in prompt
            assert "vite --host" not in prompt


class TestCreateAgentRequestSchema:
    def test_capabilities_max_10_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentRequest.model_validate(
                {
                    "name": "agent",
                    "provider": "claude_code",
                    "capabilities": [str(i) for i in range(11)],
                    "config": {},
                }
            )

    def test_create_request_rejects_mock_provider(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentRequest.model_validate(
                {
                    "name": "agent",
                    "provider": "mock",
                    "capabilities": ["testing"],
                    "config": {},
                }
            )

    def test_create_request_accepts_builtin_provider(self) -> None:
        request = CreateAgentRequest.model_validate(
            {
                "name": "agent",
                "provider": "builtin",
                "capabilities": ["reading"],
                "config": {"allowed_tools": ["read_file"]},
            }
        )

        assert request.provider == "builtin"
        assert request.config.allowed_tools == ["read_file"]

    def test_agent_out_accepts_mock_provider(self) -> None:
        agent = AgentOut.model_validate(
            {
                "id": "mock-agent",
                "name": "Mock Agent",
                "provider": "mock",
                "avatar_url": "",
                "capabilities": ["testing"],
                "system_prompt": None,
                "config": {},
                "is_builtin": True,
                "created_at": datetime.now(UTC),
            }
        )

        assert agent.provider == "mock"


class TestAgentConfigSchemaMetadata:
    def test_agent_config_numeric_bounds_match_shared_metadata(self) -> None:
        schema = AgentConfig.model_json_schema()
        properties = schema["properties"]

        for key, field in NUMERIC_CONFIG_FIELDS.items():
            property_schema = properties[key]
            numeric_schema = next(
                (
                    item
                    for item in property_schema.get("anyOf", [property_schema])
                    if "minimum" in item
                ),
                property_schema,
            )
            assert numeric_schema["minimum"] == field.minimum
            assert numeric_schema["maximum"] == field.maximum


class TestErrorStructure:
    def test_error_has_code_message_details(self) -> None:
        exc = AgentConfigValidationError(
            code="INVALID_MODEL",
            message="model is required",
            details={"provider": "claude"},
        )
        assert exc.code == "INVALID_MODEL"
        assert exc.message == "model is required"
        assert exc.details == {"provider": "claude"}


class TestOpenAPIContract:
    def test_openapi_includes_external_runtime_and_qa_config_fields(self) -> None:
        openapi = Path(__file__).parents[1] / ".." / "shared" / "openapi.yaml"
        text = openapi.resolve().read_text(encoding="utf-8")
        document = yaml.safe_load(text)
        openapi_properties = document["components"]["schemas"]["AgentConfig"]["properties"]
        schema_properties = AgentConfig.model_json_schema()["properties"]

        for field in schema_properties:
            assert field in openapi_properties

        for schema in (
            "OrchestratorRunOut",
            "OrchestratorRunDetailOut",
        ):
            assert schema in document["components"]["schemas"]

    def test_openapi_agent_config_numeric_bounds_match_shared_metadata(self) -> None:
        openapi = Path(__file__).parents[1] / ".." / "shared" / "openapi.yaml"
        document = yaml.safe_load(openapi.resolve().read_text(encoding="utf-8"))
        properties = document["components"]["schemas"]["AgentConfig"]["properties"]

        for key, field in NUMERIC_CONFIG_FIELDS.items():
            property_schema = properties[key]
            if "anyOf" in property_schema:
                property_schema = next(
                    item for item in property_schema["anyOf"] if item.get("type") != "null"
                )
            assert property_schema["minimum"] == field.minimum
            assert property_schema["maximum"] == field.maximum
