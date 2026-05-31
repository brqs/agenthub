"""Small shared utilities for external runtime adapters."""

from __future__ import annotations

import os
import shlex
from collections.abc import Sequence

from app.agents.runtime_guard import (
    redact_runtime_secrets,
    sanitize_preview_deploy_text,
)
from app.agents.types import StreamChunk


def argv(
    value: object,
    *,
    default: Sequence[str] = (),
    drop_empty: bool = False,
) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        parsed = shlex.split(value, posix=os.name != "nt")
        return parsed or list(default)
    if isinstance(value, list):
        items = [str(item) for item in value]
        if drop_empty:
            items = [item for item in items if item]
        return items or list(default)
    return [str(value)]


def truncate(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    return value[:max_chars]


def external_error_chunk(
    *,
    agent_id: str,
    provider: str,
    error_code: str,
    error: str,
) -> StreamChunk:
    return StreamChunk(
        event_type="error",
        agent_id=agent_id,
        error_code=error_code,
        error=error,
        metadata={"provider": provider},
    )


def safe_exception_message(exc: BaseException, *, max_chars: int = 500) -> str:
    message = str(exc) or exc.__class__.__name__
    return redact_runtime_secrets(message)[:max_chars]


def safe_runtime_output(
    output: str,
    *,
    max_chars: int,
    empty: str = "no output",
) -> str:
    cleaned = redact_runtime_secrets(sanitize_preview_deploy_text(output.strip()))
    return cleaned[:max_chars] or empty


def classify_external_exception(exc: BaseException) -> str:
    lowered = f"{exc.__class__.__name__}: {exc}".lower()
    if (
        "api key" in lowered
        or "api_key" in lowered
        or "credentials" in lowered
        or "authentication" in lowered
        or "unauthorized" in lowered
    ):
        return "missing_api_key"
    return "external_runtime_error"
