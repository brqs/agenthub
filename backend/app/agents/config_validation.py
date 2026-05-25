"""Agent configuration validation — B2-owned utilities."""

from __future__ import annotations

from typing import Any

SUPPORTED_PROVIDER_MODELS: dict[str, set[str]] = {
    "claude": {"claude-sonnet-4-6"},
    "openai": {"gpt-4o"},
}

SUPPORTED_UPSTREAM_PROVIDERS: set[str] = {"claude", "openai"}


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

    normalized = dict(config)

    # provider
    if provider not in SUPPORTED_PROVIDER_MODELS and provider != "custom":
        raise AgentConfigValidationError(
            code="INVALID_PROVIDER",
            message=f"Unsupported provider '{provider}'",
            details={"provider": provider},
        )

    # model
    model = normalized.get("model")
    if model is None or model == "":
        raise AgentConfigValidationError(
            code="INVALID_MODEL",
            message="model is required and must be a non-empty string",
            details={"provider": provider},
        )
    if not isinstance(model, str):
        raise AgentConfigValidationError(
            code="INVALID_MODEL",
            message="model must be a string",
            details={"provider": provider, "model": model},
        )

    # upstream_provider
    upstream_provider = normalized.get("upstream_provider")
    if upstream_provider is not None:
        if not isinstance(upstream_provider, str):
            raise AgentConfigValidationError(
                code="INVALID_UPSTREAM_PROVIDER",
                message="upstream_provider must be a string",
                details={"upstream_provider": upstream_provider},
            )
        upstream_provider = upstream_provider.lower()
        normalized["upstream_provider"] = upstream_provider

    # provider-specific rules
    if provider == "custom":
        # system_prompt required
        if not system_prompt or not isinstance(system_prompt, str) or system_prompt.strip() == "":
            raise AgentConfigValidationError(
                code="MISSING_SYSTEM_PROMPT",
                message="custom agent requires a non-empty system_prompt",
            )

        # upstream_provider required
        if upstream_provider is None:
            raise AgentConfigValidationError(
                code="INVALID_UPSTREAM_PROVIDER",
                message="custom agent requires upstream_provider (claude or openai)",
            )
        if upstream_provider not in SUPPORTED_UPSTREAM_PROVIDERS:
            raise AgentConfigValidationError(
                code="INVALID_UPSTREAM_PROVIDER",
                message=f"Unsupported upstream_provider '{upstream_provider}'",
                details={"upstream_provider": upstream_provider},
            )

        # model validated against upstream provider
        effective_model_provider = upstream_provider
    else:
        # direct providers should not carry upstream_provider
        if upstream_provider is not None:
            raise AgentConfigValidationError(
                code="INVALID_AGENT_CONFIG",
                message=f"provider '{provider}' does not allow upstream_provider",
                details={"provider": provider},
            )
        effective_model_provider = provider

    # model whitelist
    supported_models = SUPPORTED_PROVIDER_MODELS.get(effective_model_provider, set())
    if model not in supported_models:
        raise AgentConfigValidationError(
            code="INVALID_MODEL",
            message=f"Unsupported model '{model}' for provider '{effective_model_provider}'",
            details={"provider": effective_model_provider, "model": model},
        )

    # numeric fields
    _validate_numeric(normalized, "temperature", 0, 2)
    _validate_numeric(normalized, "max_tokens", 1, 16384, allow_float=False)
    _validate_numeric(normalized, "top_p", 0, 1)

    return normalized


def merge_agent_config(
    existing: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Shallow-merge patch into existing config.

    Returns a new dict; does not mutate either input.
    """
    return {**existing, **patch}
