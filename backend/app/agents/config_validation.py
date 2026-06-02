"""Agent configuration validation — B2-owned utilities."""

from __future__ import annotations

from typing import Any

from app.agents.config_fields import (
    BUILTIN_ORCHESTRATOR_FIELDS,
    CODEX_RUNTIMES,
    CODEX_SANDBOX_MODES,
    EXTERNAL_DIRECT_CHAT_FIELDS,
    EXTERNAL_RUNTIME_BUDGET_FIELDS,
    SUPPORTED_UPSTREAM_PROVIDERS,
    TOP_LEVEL_PROVIDERS,
)

QA_MODEL_BACKENDS = SUPPORTED_UPSTREAM_PROVIDERS


class AgentConfigValidationError(ValueError):
    """Raised when agent config fails validation."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def _validate_numeric(
    config: dict[str, Any],
    key: str,
    min_val: float,
    max_val: float,
    *,
    allow_float: bool = True,
) -> None:
    value = config.get(key)
    if value is None:
        return
    if isinstance(value, bool):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'{key}' must be a number, not a boolean",
            details={"field": key, "value": value},
        )
    if not isinstance(value, (int, float)):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'{key}' must be a number",
            details={"field": key, "value": value},
        )
    if not allow_float and isinstance(value, float):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'{key}' must be an integer",
            details={"field": key, "value": value},
        )
    if value < min_val or value > max_val:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'{key}' must be between {min_val} and {max_val}",
            details={"field": key, "value": value, "min": min_val, "max": max_val},
        )


def _validate_string_list(config: dict[str, Any], key: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'{key}' must be a list of strings",
            details={"field": key, "value": value},
        )


def _validate_bool(config: dict[str, Any], key: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, bool):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'{key}' must be a boolean",
            details={"field": key, "value": value},
        )


def _validate_optional_non_empty_string(config: dict[str, Any], key: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not value:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'{key}' must be a non-empty string",
            details={"field": key, "value": value},
        )


def _validate_mcp_servers(config: dict[str, Any]) -> None:
    value = config.get("mcp_servers")
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'mcp_servers' must be a list of objects",
            details={"field": "mcp_servers", "value": value},
        )


def _validate_external_runtime_config(provider: str, config: dict[str, Any]) -> None:
    for field in EXTERNAL_RUNTIME_BUDGET_FIELDS:
        _validate_numeric(
            config,
            field.key,
            field.minimum,
            field.maximum,
            allow_float=field.allow_float,
        )
    _validate_external_direct_chat_config(config)
    max_runtime = config.get("max_runtime_seconds", config.get("timeout_seconds"))
    idle_timeout = config.get("idle_timeout_seconds")
    if (
        isinstance(max_runtime, (int, float))
        and not isinstance(max_runtime, bool)
        and isinstance(idle_timeout, (int, float))
        and not isinstance(idle_timeout, bool)
        and idle_timeout > max_runtime
    ):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'idle_timeout_seconds' must be less than or equal to max runtime",
            details={
                "field": "idle_timeout_seconds",
                "value": idle_timeout,
                "max_runtime_seconds": max_runtime,
            },
        )
    if provider == "opencode":
        command = config.get("command")
        if command is not None and not isinstance(command, str | list):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message="'command' must be a string or list",
                details={"field": "command", "value": command},
            )
        _validate_string_list(config, "args")
    if provider == "codex":
        runtime = config.get("runtime")
        if runtime is not None and runtime not in CODEX_RUNTIMES:
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message="'runtime' must be one of: cli, sdk",
                details={"field": "runtime", "value": runtime},
            )
        sandbox_mode = config.get("sandbox_mode")
        if sandbox_mode is not None and sandbox_mode not in CODEX_SANDBOX_MODES:
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message=(
                    "'sandbox_mode' must be one of: read-only, workspace-write, "
                    "danger-full-access"
                ),
                details={"field": "sandbox_mode", "value": sandbox_mode},
            )


def _validate_external_direct_chat_config(config: dict[str, Any]) -> None:
    _validate_bool(config, "qa_short_circuit_enabled")
    qa_model_backend = config.get("qa_model_backend")
    if qa_model_backend is not None and (
        not isinstance(qa_model_backend, str)
        or qa_model_backend not in QA_MODEL_BACKENDS
    ):
        raise AgentConfigValidationError(
            code="INVALID_MODEL_BACKEND",
            message=f"Unsupported qa_model_backend '{qa_model_backend}'",
            details={"qa_model_backend": qa_model_backend},
        )
    _validate_optional_non_empty_string(config, "qa_model")
    _validate_optional_non_empty_string(config, "qa_classifier_model")
    for field in EXTERNAL_DIRECT_CHAT_FIELDS:
        _validate_numeric(
            config,
            field.key,
            field.minimum,
            field.maximum,
            allow_float=field.allow_float,
        )


def _validate_builtin_config(config: dict[str, Any]) -> None:
    model_backend = config.get("model_backend", "claude")
    if not isinstance(model_backend, str) or model_backend not in SUPPORTED_UPSTREAM_PROVIDERS:
        raise AgentConfigValidationError(
            code="INVALID_MODEL_BACKEND",
            message=f"Unsupported model_backend '{model_backend}'",
            details={"model_backend": model_backend},
        )
    answer_model_backend = config.get("answer_model_backend")
    if answer_model_backend is not None and (
        not isinstance(answer_model_backend, str)
        or answer_model_backend not in SUPPORTED_UPSTREAM_PROVIDERS
    ):
        raise AgentConfigValidationError(
            code="INVALID_MODEL_BACKEND",
            message=f"Unsupported answer_model_backend '{answer_model_backend}'",
            details={"answer_model_backend": answer_model_backend},
        )
    planner_model_backend = config.get("planner_model_backend")
    if planner_model_backend is not None and (
        not isinstance(planner_model_backend, str)
        or planner_model_backend not in SUPPORTED_UPSTREAM_PROVIDERS
    ):
        raise AgentConfigValidationError(
            code="INVALID_MODEL_BACKEND",
            message=f"Unsupported planner_model_backend '{planner_model_backend}'",
            details={"planner_model_backend": planner_model_backend},
        )
    answer_config = config.get("orchestrator_answer_config")
    if answer_config is not None and not isinstance(answer_config, dict):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'orchestrator_answer_config' must be an object",
            details={"field": "orchestrator_answer_config", "value": answer_config},
        )
    llm_config = config.get("orchestrator_llm_config")
    if llm_config is not None and not isinstance(llm_config, dict):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'orchestrator_llm_config' must be an object",
            details={"field": "orchestrator_llm_config", "value": llm_config},
        )
    for field in BUILTIN_ORCHESTRATOR_FIELDS:
        _validate_numeric(
            config,
            field.key,
            field.minimum,
            field.maximum,
            allow_float=field.allow_float,
        )
    _validate_bool(config, "react_enabled")
    _validate_bool(config, "react_trace_visible")
    _validate_bool(config, "llm_planning")
    _validate_bool(config, "planner_fallback_to_template")
    _validate_string_list(config, "task_fallback_agent_ids")
    _validate_bool(config, "orchestrator_memory_enabled")
    _validate_bool(config, "orchestrator_tool_calling_enabled")
    _validate_bool(config, "orchestrator_tool_trace_visible")
    _validate_bool(config, "orchestrator_parallel_enabled")
    _validate_bool(config, "orchestrator_evaluation_enabled")
    _validate_bool(config, "orchestrator_test_runner_enabled")
    _validate_string_list(config, "orchestrator_test_command_allowlist")
    _validate_mcp_servers(config)


def validate_agent_config(
    *,
    provider: str,
    config: dict[str, Any],
    system_prompt: str | None,
) -> dict[str, Any]:
    """Validate and normalize an agent config dict.

    Returns a shallow-copied, normalized config dict.
    Raises AgentConfigValidationError on failure.
    """
    if not isinstance(config, dict):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="config must be an object",
        )

    _ = system_prompt
    normalized = dict(config)

    provider = provider.lower()

    # provider
    if provider not in TOP_LEVEL_PROVIDERS:
        raise AgentConfigValidationError(
            code="INVALID_PROVIDER",
            message=f"Unsupported provider '{provider}'",
            details={"provider": provider},
        )

    if provider == "mock":
        return normalized

    if provider in {"claude_code", "codex", "opencode"}:
        _validate_external_runtime_config(provider, normalized)
        return normalized

    if provider == "builtin":
        _validate_builtin_config(normalized)
        return normalized

    raise AgentConfigValidationError(
        code="INVALID_PROVIDER",
        message=f"Unsupported provider '{provider}'",
        details={"provider": provider},
    )


def merge_agent_config(
    existing: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Shallow-merge patch into existing config.

    Returns a new dict; does not mutate either input.
    """
    return {**existing, **patch}
