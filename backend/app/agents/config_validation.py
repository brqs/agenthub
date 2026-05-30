"""Agent configuration validation — B2-owned utilities."""

from __future__ import annotations

from typing import Any

SUPPORTED_UPSTREAM_PROVIDERS: set[str] = {"claude", "deepseek", "openai"}
TOP_LEVEL_PROVIDERS: set[str] = {
    "claude_code",
    "codex",
    "opencode",
    "builtin",
    "mock",
}
CODEX_RUNTIMES: set[str] = {"cli", "sdk"}
CODEX_SANDBOX_MODES: set[str] = {"read-only", "workspace-write", "danger-full-access"}
EXTERNAL_RUNTIME_BUDGET_KEYS = (
    "timeout_seconds",
    "max_runtime_seconds",
    "idle_timeout_seconds",
    "heartbeat_interval_seconds",
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
    for key in EXTERNAL_RUNTIME_BUDGET_KEYS:
        _validate_numeric(config, key, 1, 3600)
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
    _validate_numeric(config, "qa_max_tokens", 1, 32000, allow_float=False)
    _validate_numeric(config, "qa_classifier_max_tokens", 1, 1024, allow_float=False)
    _validate_numeric(config, "qa_temperature", 0, 2)
    _validate_numeric(config, "qa_request_timeout_seconds", 1, 120)


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
    answer_config = config.get("orchestrator_answer_config")
    if answer_config is not None and not isinstance(answer_config, dict):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'orchestrator_answer_config' must be an object",
            details={"field": "orchestrator_answer_config", "value": answer_config},
        )
    _validate_numeric(config, "max_iterations", 1, 50, allow_float=False)
    _validate_bool(config, "react_enabled")
    _validate_bool(config, "react_trace_visible")
    _validate_numeric(config, "react_decision_max_tokens", 1, 4096, allow_float=False)
    _validate_string_list(config, "task_fallback_agent_ids")
    _validate_numeric(config, "max_task_attempts", 1, 3, allow_float=False)
    _validate_numeric(
        config,
        "task_result_context_max_chars",
        1,
        32000,
        allow_float=False,
    )
    _validate_numeric(
        config,
        "task_result_item_max_chars",
        1,
        8000,
        allow_float=False,
    )
    _validate_bool(config, "orchestrator_memory_enabled")
    _validate_numeric(
        config,
        "orchestrator_memory_recent_runs",
        1,
        10,
        allow_float=False,
    )
    _validate_numeric(
        config,
        "orchestrator_memory_context_max_chars",
        1,
        32000,
        allow_float=False,
    )
    _validate_bool(config, "orchestrator_tool_calling_enabled")
    _validate_bool(config, "orchestrator_tool_trace_visible")
    _validate_numeric(
        config,
        "orchestrator_tool_max_iterations",
        1,
        50,
        allow_float=False,
    )
    _validate_numeric(
        config,
        "orchestrator_tool_result_max_chars",
        1,
        32000,
        allow_float=False,
    )
    _validate_numeric(
        config,
        "orchestrator_tool_read_max_bytes",
        1,
        1048576,
        allow_float=False,
    )
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
