"""Compatibility exports for legacy provider resilience imports."""

from app.agents.model_gateway.resilience import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    MAX_RETRIES_LIMIT,
    ProviderErrorClasses,
    ProviderErrorCode,
    ResilienceConfig,
    classify_exception,
    error_chunk,
    exception_classes,
    is_retryable_error,
    parse_resilience_config,
    safe_error_message,
    sleep_before_retry,
)

__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "DEFAULT_RETRY_BACKOFF_SECONDS",
    "MAX_RETRIES_LIMIT",
    "ProviderErrorClasses",
    "ProviderErrorCode",
    "ResilienceConfig",
    "classify_exception",
    "error_chunk",
    "exception_classes",
    "is_retryable_error",
    "parse_resilience_config",
    "safe_error_message",
    "sleep_before_retry",
]
