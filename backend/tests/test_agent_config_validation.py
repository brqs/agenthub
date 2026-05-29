"""Tests for agent config validation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.config_validation import (
    AgentConfigValidationError,
    merge_agent_config,
    validate_agent_config,
)
from app.schemas.agent import AgentOut, CreateAgentRequest
from app.seeds.seed_agents import BUILTIN_AGENTS


class TestValidConfigs:
    def test_valid_claude_code_config(self) -> None:
        config = {
            "sdk_options": {},
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 180,
            "heartbeat_interval_seconds": 15,
            "qa_short_circuit_enabled": True,
            "qa_model_backend": "deepseek",
            "qa_max_tokens": 2048,
            "qa_classifier_max_tokens": 128,
            "qa_temperature": 0.2,
            "qa_request_timeout_seconds": 20,
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
            "max_iterations": 10,
            "react_enabled": True,
            "react_trace_visible": False,
            "react_decision_max_tokens": 1024,
            "mcp_servers": [],
            "task_fallback_agent_ids": ["codex-helper"],
            "max_task_attempts": 2,
            "task_result_context_max_chars": 4000,
            "task_result_item_max_chars": 1200,
        }
        result = validate_agent_config(
            provider="builtin",
            config=config,
            system_prompt=None,
        )
        assert result == config


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

            assert config["qa_short_circuit_enabled"] is True
            assert config["qa_model_backend"] == "deepseek"
            assert config["qa_max_tokens"] == 2048
            assert config["qa_classifier_max_tokens"] == 128
            assert config["qa_temperature"] == 0.2
            assert config["qa_request_timeout_seconds"] == 20

    def test_seed_orchestrator_enables_react_defaults(self) -> None:
        orchestrator = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "orchestrator")
        config = orchestrator["config"]

        assert config["react_enabled"] is True
        assert config["react_trace_visible"] is True

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
            assert "python3 -m http.server 8082" not in prompt
            assert "npm run dev" not in prompt
            assert "pnpm dev" not in prompt
            assert "vite --host" not in prompt

    def test_web_designer_prompt_documents_native_tool_path_contract(self) -> None:
        agent = next(agent for agent in BUILTIN_AGENTS if agent["id"] == "web-designer")
        prompt = agent["system_prompt"]

        assert "path argument" in prompt
        assert "workspace-relative path such as snake.html" in prompt
        assert "absolute paths" in prompt
        assert "Treat the latest user message as the only active request" in prompt
        assert "Do not run, suggest, output, or call tools" in prompt
        assert "platform preview/deploy must be started outside the agent runtime" in prompt


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

        for field in (
            "max_runtime_seconds",
            "idle_timeout_seconds",
            "heartbeat_interval_seconds",
            "qa_short_circuit_enabled",
            "qa_model_backend",
            "qa_max_tokens",
            "qa_classifier_max_tokens",
            "qa_temperature",
            "qa_request_timeout_seconds",
            "task_fallback_agent_ids",
            "max_task_attempts",
            "task_result_context_max_chars",
            "task_result_item_max_chars",
            "react_enabled",
            "react_trace_visible",
            "react_decision_max_tokens",
        ):
            assert field in text
