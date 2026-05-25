"""Shared retry and error mapping helpers for provider adapters."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from app.agents.types import StreamChunk

ProviderErrorCode = Literal[
    "missing_api_key",
    "rate_limit",
    "timeout",
    "connection_error",
    "upstream_error",
]

DEFAULT_MAX_RETRIES = 1
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RETRIES_LIMIT = 3


@dataclass(frozen=True)
class ResilienceConfig:
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    retry_on_rate_limit: bool = False


@dataclass(frozen=True)
class ProviderErrorClasses:
    rate_limit: tuple[type[BaseException], ...] = ()
    timeout: tuple[type[BaseException], ...] = ()
    connection: tuple[type[BaseException], ...] = ()
    api: tuple[type[BaseException], ...] = ()


def parse_resilience_config(config: dict[str, Any]) -> ResilienceConfig:
    """Parse retry/timeout settings without letting bad config raise."""
    max_retries = _read_int(config, "max_retries", DEFAULT_MAX_RETRIES)
    max_retries = max(0, min(max_retries, MAX_RETRIES_LIMIT))

    retry_backoff_seconds = _read_float(
        config,
        "retry_backoff_seconds",
        DEFAULT_RETRY_BACKOFF_SECONDS,
    )
    retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    request_timeout_seconds = _read_float(
        config,
        "request_timeout_seconds",
        DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    if request_timeout_seconds <= 0:
        request_timeout_seconds = DEFAULT_REQUEST_TIMEOUT_SECONDS

    retry_on_rate_limit = _read_bool(config, "retry_on_rate_limit", False)

    return ResilienceConfig(
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        request_timeout_seconds=request_timeout_seconds,
        retry_on_rate_limit=retry_on_rate_limit,
    )


def error_chunk(
    *,
    agent_id: str,
    provider: str,
    error_code: ProviderErrorCode,
    error: str,
    attempts: int,
    retryable: bool,
) -> StreamChunk:
    return StreamChunk(
        event_type="error",
        agent_id=agent_id,
        error_code=error_code,
        error=error,
        metadata={
            "provider": provider,
            "attempts": attempts,
            "retryable": retryable,
        },
    )


def classify_exception(
    exc: BaseException,
    error_classes: ProviderErrorClasses,
) -> ProviderErrorCode:
    if _is_instance(exc, error_classes.rate_limit):
        return "rate_limit"
    if isinstance(exc, TimeoutError) or _is_instance(exc, error_classes.timeout):
        return "timeout"
    if isinstance(exc, ConnectionError) or _is_instance(exc, error_classes.connection):
        return "connection_error"
    if _is_instance(exc, error_classes.api):
        return "upstream_error"
    return "upstream_error"


def is_retryable_error(
    error_code: ProviderErrorCode,
    config: ResilienceConfig,
) -> bool:
    if error_code == "rate_limit":
        return config.retry_on_rate_limit
    return error_code in {"timeout", "connection_error", "upstream_error"}


async def sleep_before_retry(
    config: ResilienceConfig,
    completed_attempts: int,
) -> None:
    if config.retry_backoff_seconds <= 0:
        return
    await asyncio.sleep(config.retry_backoff_seconds * completed_attempts)


def safe_error_message(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__


def exception_classes(*classes: Any) -> tuple[type[BaseException], ...]:
    return tuple(
        cls
        for cls in classes
        if isinstance(cls, type) and issubclass(cls, BaseException)
    )


def _read_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return int(value)


def _read_float(config: dict[str, Any], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _read_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        return default
    return value


def _is_instance(
    exc: BaseException,
    classes: tuple[type[BaseException], ...],
) -> bool:
    return bool(classes) and isinstance(exc, classes)
