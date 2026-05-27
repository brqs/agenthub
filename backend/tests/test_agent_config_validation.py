"""Tests for agent config validation."""

from __future__ import annotations

from datetime import UTC, datetime

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
        config = {"sdk_options": {}}
        result = validate_agent_config(
            provider="claude_code",
            config=config,
            system_prompt=None,
        )
        assert result == {"sdk_options": {}}

    def test_valid_codex_config(self) -> None:
        config = {"model": "gpt-4.1", "timeout_seconds": 120}
        result = validate_agent_config(
            provider="codex",
            config=config,
            system_prompt=None,
        )
        assert result["model"] == "gpt-4.1"
        assert result["timeout_seconds"] == 120

    def test_valid_opencode_config(self) -> None:
        config = {"command": "opencode", "args": ["run", "--jsonl"], "timeout_seconds": 120}
        result = validate_agent_config(
            provider="opencode",
            config=config,
            system_prompt=None,
        )
        assert result["command"] == "opencode"
        assert result["args"] == ["run", "--jsonl"]

    def test_valid_builtin_config(self) -> None:
        config = {"model_backend": "claude", "max_iterations": 10, "mcp_servers": []}
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

    def test_timeout_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude_code",
                config={"timeout_seconds": True},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_max_iterations_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="builtin",
                config={"max_iterations": False},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message


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
