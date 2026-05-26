"""
OpenAIAdapter — OpenAI / Codex streaming.

Uses `openai.AsyncOpenAI` to stream text deltas, feeds them into
`StreamingArtifactParser` to split text vs code blocks, and yields standard
`StreamChunk` events for B1 SSE consumption.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import openai

from app.agents.adapters.resilience import (
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
from app.agents.artifact_parser import StreamingArtifactParser
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.config import settings


class OpenAIAdapter(BaseAgentAdapter):
    """Adapter for OpenAI ChatGPT / Codex models."""

    provider = "openai"
    default_model = "gpt-4o"
    api_key_setting = "openai_api_key"
    base_url_setting = "openai_base_url"
    display_name = "OpenAI"

    def _api_key(self) -> str:
        return str(getattr(settings, self.api_key_setting))

    def _base_url(self) -> str:
        return str(getattr(settings, self.base_url_setting))

    def _create_client(self) -> openai.AsyncOpenAI:
        """Build an async OpenAI-compatible client from settings."""
        kwargs: dict[str, Any] = {"api_key": self._api_key()}
        if self._base_url():
            kwargs["base_url"] = self._base_url()
        return openai.AsyncOpenAI(**kwargs)

    def _provider_error_classes(self) -> ProviderErrorClasses:
        return ProviderErrorClasses(
            rate_limit=exception_classes(getattr(openai, "RateLimitError", None)),
            timeout=exception_classes(getattr(openai, "APITimeoutError", None)),
            connection=exception_classes(getattr(openai, "APIConnectionError", None)),
            api=exception_classes(getattr(openai, "APIError", None)),
        )

    def _error_chunk(
        self,
        *,
        error_code: ProviderErrorCode,
        error: str,
        attempts: int,
        retryable: bool,
    ) -> StreamChunk:
        return error_chunk(
            agent_id=self.agent_id,
            provider=self.provider,
            error_code=error_code,
            error=error,
            attempts=attempts,
            retryable=retryable,
        )

    async def _open_stream_with_retries(
        self,
        client: Any,
        stream_kwargs: dict[str, Any],
        resilience: ResilienceConfig,
    ) -> tuple[Any | None, StreamChunk | None, int]:
        error_classes = self._provider_error_classes()
        max_attempts = resilience.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                stream = await asyncio.wait_for(
                    client.chat.completions.create(**stream_kwargs),
                    timeout=resilience.request_timeout_seconds,
                )
                return stream, None, attempt
            except Exception as exc:
                error_code = classify_exception(exc, error_classes)
                retryable = is_retryable_error(error_code, resilience)
                if retryable and attempt <= resilience.max_retries:
                    await sleep_before_retry(resilience, attempt)
                    continue
                return (
                    None,
                    self._error_chunk(
                        error_code=error_code,
                        error=safe_error_message(exc),
                        attempts=attempt,
                        retryable=retryable,
                    ),
                    attempt,
                )

        return None, None, max_attempts

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)
        resilience = parse_resilience_config(merged)
        model = merged.get("model") or self.default_model
        temperature = merged.get("temperature")
        if temperature is None:
            temperature = 0.7
        max_tokens = merged.get("max_tokens")
        if max_tokens is None:
            max_tokens = 4096

        effective_system = self.effective_system_prompt(system_prompt) or ""

        # Merge system messages into a single system message.
        openai_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                if effective_system:
                    effective_system += "\n" + msg.content
                else:
                    effective_system = msg.content
            elif msg.content:
                openai_messages.append({"role": msg.role, "content": msg.content})

        if effective_system:
            openai_messages.insert(0, {"role": "system", "content": effective_system})

        yield StreamChunk(event_type="start", agent_id=self.agent_id)

        if not self._api_key():
            yield self._error_chunk(
                error_code="missing_api_key",
                error=f"{self.display_name} API key is not configured",
                attempts=0,
                retryable=False,
            )
            return

        try:
            client = self._create_client()
        except Exception as exc:
            error_code = classify_exception(exc, self._provider_error_classes())
            yield self._error_chunk(
                error_code=error_code,
                error=safe_error_message(exc),
                attempts=0,
                retryable=False,
            )
            return

        parser = StreamingArtifactParser()

        stream_kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        stream, setup_error, attempts = await self._open_stream_with_retries(
            client,
            stream_kwargs,
            resilience,
        )
        if setup_error is not None:
            yield setup_error
            return
        if stream is None:
            yield self._error_chunk(
                error_code="upstream_error",
                error=f"{self.display_name} stream was not opened",
                attempts=attempts,
                retryable=False,
            )
            return

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                for parser_chunk in parser.feed(delta):
                    yield parser_chunk

            for parser_chunk in parser.flush():
                yield parser_chunk

            total_blocks = parser.block_index + 1 if parser.block_index >= 0 else 0
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=total_blocks,
            )
        except Exception as exc:
            for parser_chunk in parser.flush():
                yield parser_chunk

            error_code = classify_exception(exc, self._provider_error_classes())
            yield self._error_chunk(
                error_code=error_code,
                error=safe_error_message(exc),
                attempts=attempts,
                retryable=False,
            )
