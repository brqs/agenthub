"""Agent configuration validation — B2-owned utilities."""

from __future__ import annotations

import re
from typing import Any

from app.agents.config_fields import (
    BUILTIN_ORCHESTRATOR_FIELDS,
    CLAUDE_CODE_RUNTIMES,
    CODEX_RUNTIMES,
    CODEX_SANDBOX_MODES,
    CONTEXT_BUDGET_FIELDS,
    EXTERNAL_DIRECT_CHAT_FIELDS,
    EXTERNAL_RUNTIME_BUDGET_FIELDS,
    SUPPORTED_UPSTREAM_PROVIDERS,
    TOP_LEVEL_PROVIDERS,
)

QA_MODEL_BACKENDS = SUPPORTED_UPSTREAM_PROVIDERS
BUILTIN_NATIVE_TOOL_NAMES = {"read_file", "write_file", "bash"}
MCP_TOOL_NAME_RE = re.compile(r"^mcp_([^_][A-Za-z0-9_-]*)__(.+)$")
MEMORY_POLICIES = {"none", "conversation", "project", "user"}
CLARIFICATION_POLICIES = {"ask_first", "balanced", "decide_with_defaults"}
RUN_COMMAND_POLICIES = {"never", "ask", "auto_low_risk"}
NETWORK_POLICIES = {"never", "ask", "allowlisted"}
ASK_POLICIES = {"never", "ask"}
FORBIDDEN_SECRET_CONFIG_KEYS = {
    "api_key",
    "apikey",
    "secret",
    "access_token",
    "authorization",
}
WRAPPER_MODE = "server_agent_wrapper"
WRAPPER_BASE_PROVIDERS = {
    "claude-code": "claude_code",
    "codex-helper": "codex",
    "opencode-helper": "opencode",
}
WRAPPER_PROFILE_STRING_FIELDS = {
    "role",
    "purpose",
    "planning_profile",
    "output_style",
}
WRAPPER_PROFILE_LIST_FIELDS = {
    "planning_strengths",
    "planning_weaknesses",
    "preferred_task_types",
    "capabilities",
    "boundaries",
}


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


def _validate_allowed_tools(config: dict[str, Any]) -> None:
    value = config.get("allowed_tools")
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'allowed_tools' must be a list of strings",
            details={"field": "allowed_tools", "value": value},
        )

    seen: set[str] = set()
    server_names = {
        str(server["name"])
        for server in config.get("mcp_servers", [])
        if isinstance(server, dict) and isinstance(server.get("name"), str)
    }
    for tool_name in value:
        if not tool_name:
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message="'allowed_tools' entries must be non-empty strings",
                details={"field": "allowed_tools", "value": value},
            )
        if tool_name in seen:
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message="'allowed_tools' entries must be unique",
                details={"field": "allowed_tools", "value": tool_name},
            )
        seen.add(tool_name)
        if tool_name in BUILTIN_NATIVE_TOOL_NAMES:
            continue
        match = MCP_TOOL_NAME_RE.match(tool_name)
        if match and match.group(1) in server_names and match.group(2):
            continue
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=(
                "'allowed_tools' entries must be builtin native tools or "
                "configured MCP tools"
            ),
            details={"field": "allowed_tools", "value": tool_name},
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


def _validate_builder_profile(config: dict[str, Any]) -> None:
    value = config.get("builder_profile")
    if value is None:
        return
    if not isinstance(value, dict):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'builder_profile' must be an object",
            details={"field": "builder_profile", "value": value},
        )
    for key in ("role", "purpose", "tone", "output_style"):
        raw = value.get(key)
        if raw is not None and not isinstance(raw, str):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message=f"'builder_profile.{key}' must be a string",
                details={"field": f"builder_profile.{key}", "value": raw},
            )
    for key in ("goals", "do_not_do", "starters"):
        raw = value.get(key)
        if raw is not None and (
            not isinstance(raw, list) or not all(isinstance(item, str) for item in raw)
        ):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message=f"'builder_profile.{key}' must be a list of strings",
                details={"field": f"builder_profile.{key}", "value": raw},
            )
    clarification_policy = value.get("clarification_policy")
    if clarification_policy is not None and clarification_policy not in CLARIFICATION_POLICIES:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'builder_profile.clarification_policy' is not supported",
            details={
                "field": "builder_profile.clarification_policy",
                "value": clarification_policy,
            },
        )


def _validate_permissions(config: dict[str, Any]) -> None:
    value = config.get("permissions")
    if value is None:
        return
    if not isinstance(value, dict):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'permissions' must be an object",
            details={"field": "permissions", "value": value},
        )
    for key in ("workspace_read", "workspace_write"):
        raw = value.get(key)
        if raw is not None and not isinstance(raw, bool):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message=f"'permissions.{key}' must be a boolean",
                details={"field": f"permissions.{key}", "value": raw},
            )
    _validate_permission_choice(value, "run_commands", RUN_COMMAND_POLICIES)
    _validate_permission_choice(value, "network", NETWORK_POLICIES)
    _validate_permission_choice(value, "deploy", ASK_POLICIES)
    _validate_permission_choice(value, "external_accounts", ASK_POLICIES)


def _validate_permission_choice(
    permissions: dict[str, Any],
    key: str,
    allowed: set[str],
) -> None:
    raw = permissions.get(key)
    if raw is None:
        return
    if not isinstance(raw, str) or raw not in allowed:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message=f"'permissions.{key}' is not supported",
            details={"field": f"permissions.{key}", "value": raw},
        )


def _validate_memory_policy(config: dict[str, Any]) -> None:
    value = config.get("memory_policy")
    if value is None:
        return
    if not isinstance(value, str) or value not in MEMORY_POLICIES:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'memory_policy' is not supported",
            details={"field": "memory_policy", "value": value},
        )


def _validate_wrapper_profile(config: dict[str, Any], *, provider: str) -> None:
    mode = config.get("custom_agent_mode")
    if mode is None:
        return
    if mode != WRAPPER_MODE:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'custom_agent_mode' must be 'server_agent_wrapper'",
            details={"field": "custom_agent_mode", "value": mode},
        )
    base_agent_id = config.get("base_agent_id")
    if base_agent_id not in WRAPPER_BASE_PROVIDERS:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'base_agent_id' must reference a supported server Agent",
            details={"field": "base_agent_id", "value": base_agent_id},
        )
    expected_provider = WRAPPER_BASE_PROVIDERS[str(base_agent_id)]
    if provider != expected_provider:
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'base_agent_id' does not match the selected provider",
            details={
                "field": "base_agent_id",
                "value": base_agent_id,
                "provider": provider,
                "expected_provider": expected_provider,
            },
        )
    profile = config.get("wrapper_profile")
    if not isinstance(profile, dict):
        raise AgentConfigValidationError(
            code="INVALID_AGENT_CONFIG",
            message="'wrapper_profile' must be an object",
            details={"field": "wrapper_profile", "value": profile},
        )
    for key in WRAPPER_PROFILE_STRING_FIELDS:
        value = profile.get(key)
        if value is not None and not isinstance(value, str):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message=f"'wrapper_profile.{key}' must be a string",
                details={"field": f"wrapper_profile.{key}", "value": value},
            )
    for key in WRAPPER_PROFILE_LIST_FIELDS:
        value = profile.get(key)
        if value is not None and (
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
        ):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message=f"'wrapper_profile.{key}' must be a list of strings",
                details={"field": f"wrapper_profile.{key}", "value": value},
            )


def _validate_no_inline_secrets(value: Any, path: str = "config") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text.lower() in FORBIDDEN_SECRET_CONFIG_KEYS:
                raise AgentConfigValidationError(
                    code="INVALID_AGENT_CONFIG",
                    message="Agent config cannot contain inline API keys or secrets",
                    details={"field": f"{path}.{key_text}"},
                )
            _validate_no_inline_secrets(child, f"{path}.{key_text}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_no_inline_secrets(child, f"{path}[{index}]")


def _validate_external_runtime_config(provider: str, config: dict[str, Any]) -> None:
    _validate_wrapper_profile(config, provider=provider)
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
    if provider == "claude_code":
        runtime = config.get("runtime")
        if runtime is not None and runtime not in CLAUDE_CODE_RUNTIMES:
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message="'runtime' must be one of: cli, sdk",
                details={"field": "runtime", "value": runtime},
            )
        command = config.get("command")
        if command is not None and not isinstance(command, str | list):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message="'command' must be a string or list",
                details={"field": "command", "value": command},
            )
    if provider == "codex":
        command = config.get("command")
        if command is not None and not isinstance(command, str | list):
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message="'command' must be a string or list",
                details={"field": "command", "value": command},
            )
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


def _validate_context_budget_config(config: dict[str, Any]) -> None:
    for field in CONTEXT_BUDGET_FIELDS:
        _validate_numeric(
            config,
            field.key,
            field.minimum,
            field.maximum,
            allow_float=field.allow_float,
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
    response_polish_backend = config.get("orchestrator_response_polish_model_backend")
    if response_polish_backend is not None and (
        not isinstance(response_polish_backend, str)
        or response_polish_backend not in SUPPORTED_UPSTREAM_PROVIDERS
    ):
        raise AgentConfigValidationError(
            code="INVALID_MODEL_BACKEND",
            message=(
                "Unsupported orchestrator_response_polish_model_backend "
                f"'{response_polish_backend}'"
            ),
            details={
                "orchestrator_response_polish_model_backend": response_polish_backend
            },
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
    _validate_bool(config, "available_agents_authoritative")
    _validate_bool(config, "clarification_gate_enabled")
    _validate_bool(config, "workspace_docs_enabled")
    _validate_string_list(config, "task_fallback_agent_ids")
    _validate_bool(config, "orchestrator_memory_enabled")
    _validate_bool(config, "orchestrator_tool_calling_enabled")
    _validate_bool(config, "orchestrator_tool_trace_visible")
    _validate_bool(config, "orchestrator_group_messages_enabled")
    _validate_bool(config, "orchestrator_process_block_enabled")
    _validate_bool(config, "orchestrator_response_polish_enabled")
    _validate_bool(config, "orchestrator_parallel_enabled")
    _validate_bool(config, "orchestrator_evaluation_enabled")
    _validate_bool(config, "orchestrator_test_runner_enabled")
    _validate_string_list(config, "orchestrator_test_command_allowlist")
    _validate_mcp_servers(config)
    _validate_allowed_tools(config)
    _validate_builder_profile(config)
    _validate_permissions(config)
    _validate_memory_policy(config)


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
    _validate_no_inline_secrets(normalized)
    _validate_context_budget_config(normalized)

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
