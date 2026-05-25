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
    def test_valid_claude_config(self) -> None:
        config = {"model": "claude-sonnet-4-6", "temperature": 0.7, "max_tokens": 4096}
        result = validate_agent_config(
            provider="claude",
            config=config,
            system_prompt=None,
        )
        assert result["model"] == "claude-sonnet-4-6"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 4096

    def test_valid_openai_config(self) -> None:
        config = {"model": "gpt-4o", "temperature": 0.7, "max_tokens": 4096}
        result = validate_agent_config(
            provider="openai",
            config=config,
            system_prompt=None,
        )
        assert result["model"] == "gpt-4o"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 4096

    def test_valid_deepseek_config(self) -> None:
        config = {"model": "deepseek-v4-flash", "temperature": 0.7, "max_tokens": 4096}
        result = validate_agent_config(
            provider="deepseek",
            config=config,
            system_prompt=None,
        )
        assert result["model"] == "deepseek-v4-flash"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 4096


class TestCustomAgentRules:
    def test_custom_config_requires_system_prompt_none(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="custom",
                config={"model": "claude-sonnet-4-6", "upstream_provider": "claude"},
                system_prompt=None,
            )
        assert exc_info.value.code == "MISSING_SYSTEM_PROMPT"

    def test_custom_config_requires_system_prompt_empty(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="custom",
                config={"model": "claude-sonnet-4-6", "upstream_provider": "claude"},
                system_prompt="",
            )
        assert exc_info.value.code == "MISSING_SYSTEM_PROMPT"

    def test_custom_config_requires_system_prompt_whitespace(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="custom",
                config={"model": "claude-sonnet-4-6", "upstream_provider": "claude"},
                system_prompt="   ",
            )
        assert exc_info.value.code == "MISSING_SYSTEM_PROMPT"

    def test_custom_config_requires_upstream_provider(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="custom",
                config={"model": "claude-sonnet-4-6"},
                system_prompt="You are a test agent.",
            )
        assert exc_info.value.code == "INVALID_UPSTREAM_PROVIDER"

    def test_custom_config_accepts_claude_upstream(self) -> None:
        config = {"model": "claude-sonnet-4-6", "upstream_provider": "claude"}
        result = validate_agent_config(
            provider="custom",
            config=config,
            system_prompt="You are a test agent.",
        )
        assert result["upstream_provider"] == "claude"
        assert result["model"] == "claude-sonnet-4-6"

    def test_custom_config_accepts_openai_upstream(self) -> None:
        config = {"model": "gpt-4o", "upstream_provider": "openai"}
        result = validate_agent_config(
            provider="custom",
            config=config,
            system_prompt="You are a test agent.",
        )
        assert result["upstream_provider"] == "openai"
        assert result["model"] == "gpt-4o"

    def test_custom_config_accepts_deepseek_upstream(self) -> None:
        config = {"model": "deepseek-v4-pro", "upstream_provider": "deepseek"}
        result = validate_agent_config(
            provider="custom",
            config=config,
            system_prompt="You are a test agent.",
        )
        assert result["upstream_provider"] == "deepseek"
        assert result["model"] == "deepseek-v4-pro"

    def test_custom_model_validated_against_upstream(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="custom",
                config={"model": "claude-sonnet-4-6", "upstream_provider": "openai"},
                system_prompt="You are a test agent.",
            )
        assert exc_info.value.code == "INVALID_MODEL"

    def test_upstream_provider_case_insensitive_and_normalized(self) -> None:
        config = {"model": "gpt-4o", "upstream_provider": "OpenAI"}
        result = validate_agent_config(
            provider="custom",
            config=config,
            system_prompt="You are a test agent.",
        )
        assert result["upstream_provider"] == "openai"


class TestDirectProviderRules:
    def test_direct_provider_rejects_upstream_provider_claude(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "upstream_provider": "openai"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_direct_provider_rejects_upstream_provider_openai(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="openai",
                config={"model": "gpt-4o", "upstream_provider": "claude"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_direct_provider_rejects_upstream_provider_deepseek(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="deepseek",
                config={
                    "model": "deepseek-v4-flash",
                    "upstream_provider": "openai",
                },
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"


class TestModelValidation:
    def test_missing_model_rejected_none(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"temperature": 0.7},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL"

    def test_missing_model_rejected_empty(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": ""},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL"

    def test_deepseek_unsupported_model_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="deepseek",
                config={"model": "deepseek-chat"},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_MODEL"


class TestNumericValidation:
    def test_temperature_zero_is_allowed(self) -> None:
        config = {"model": "claude-sonnet-4-6", "temperature": 0}
        result = validate_agent_config(
            provider="claude",
            config=config,
            system_prompt=None,
        )
        assert result["temperature"] == 0

    def test_temperature_out_of_range_rejected_negative(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "temperature": -0.1},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_temperature_out_of_range_rejected_over(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "temperature": 2.1},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_max_tokens_out_of_range_rejected_zero(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "max_tokens": 0},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_max_tokens_out_of_range_rejected_large(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "max_tokens": 20000},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_max_tokens_float_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "max_tokens": 1.5},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "integer" in exc_info.value.message

    def test_top_p_out_of_range_rejected_negative(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "top_p": -0.1},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_top_p_out_of_range_rejected_over(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "top_p": 1.1},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"

    def test_temperature_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "temperature": True},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_max_tokens_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "max_tokens": True},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message

    def test_top_p_bool_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config={"model": "claude-sonnet-4-6", "top_p": False},
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "boolean" in exc_info.value.message


class TestImmutability:
    def test_validation_does_not_mutate_input_config(self) -> None:
        original = {"model": "claude-sonnet-4-6", "temperature": 0.7}
        config_copy = dict(original)
        validate_agent_config(
            provider="claude",
            config=config_copy,
            system_prompt=None,
        )
        assert config_copy == original


class TestConfigType:
    def test_config_none_rejected(self) -> None:
        with pytest.raises(AgentConfigValidationError) as exc_info:
            validate_agent_config(
                provider="claude",
                config=None,  # type: ignore[arg-type]
                system_prompt=None,
            )
        assert exc_info.value.code == "INVALID_AGENT_CONFIG"
        assert "object" in exc_info.value.message


class TestMergeAgentConfig:
    def test_merge_agent_config_preserves_existing_model(self) -> None:
        existing = {"model": "claude-sonnet-4-6", "temperature": 0.7}
        patch = {"temperature": 0.5}
        merged = merge_agent_config(existing, patch)
        assert merged["model"] == "claude-sonnet-4-6"
        assert merged["temperature"] == 0.5


class TestBuiltinAgents:
    def test_builtin_agents_pass_validation(self) -> None:
        for agent in BUILTIN_AGENTS:
            result = validate_agent_config(
                provider=agent["provider"],
                config=agent["config"],
                system_prompt=agent["system_prompt"],
            )
            assert isinstance(result, dict)


class TestCreateAgentRequestSchema:
    def test_capabilities_max_10_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentRequest.model_validate(
                {
                    "name": "agent",
                    "provider": "claude",
                    "capabilities": [str(i) for i in range(11)],
                    "config": {"model": "claude-sonnet-4-6"},
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
