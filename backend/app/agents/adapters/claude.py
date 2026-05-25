"""
ClaudeAdapter — Anthropic streaming.

Uses `anthropic.AsyncAnthropic` to stream text deltas, feeds them into
`StreamingArtifactParser` to split text vs code blocks, and yields standard
`StreamChunk` events for B1 SSE consumption.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import anthropic

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
from app.agents.types import ChatMessage, StreamChunk
from app.core.config import settings


class ClaudeAdapter(BaseAgentAdapter):
    """Adapter for Anthropic Claude models."""

    provider = "claude"

    def _create_client(self) -> anthropic.AsyncAnthropic:
        """Build an async Anthropic client from settings."""
        kwargs: dict[str, Any] = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            kwargs["base_url"] = settings.anthropic_base_url
        return anthropic.AsyncAnthropic(**kwargs)

    def _provider_error_classes(self) -> ProviderErrorClasses:
        return ProviderErrorClasses(
            rate_limit=exception_classes(getattr(anthropic, "RateLimitError", None)),
            timeout=exception_classes(getattr(anthropic, "APITimeoutError", None)),
            connection=exception_classes(getattr(anthropic, "APIConnectionError", None)),
            api=exception_classes(getattr(anthropic, "APIError", None)),
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
    ) -> tuple[Any | None, Any | None, StreamChunk | None, int]:
        error_classes = self._provider_error_classes()
        max_attempts = resilience.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                stream_manager = client.messages.stream(**stream_kwargs)
                stream = await asyncio.wait_for(
                    stream_manager.__aenter__(),
                    timeout=resilience.request_timeout_seconds,
                )
                return stream_manager, stream, None, attempt
            except Exception as exc:
                error_code = classify_exception(exc, error_classes)
                retryable = is_retryable_error(error_code, resilience)
                if retryable and attempt <= resilience.max_retries:
                    await sleep_before_retry(resilience, attempt)
                    continue
                return (
                    None,
                    None,
                    self._error_chunk(
                        error_code=error_code,
                        error=safe_error_message(exc),
                        attempts=attempt,
                        retryable=retryable,
                    ),
                    attempt,
                )

        return None, None, None, max_attempts

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)
        resilience = parse_resilience_config(merged)
        model = merged.get("model") or "claude-sonnet-4-6"
        temperature = merged.get("temperature")
        if temperature is None:
            temperature = 0.7
        max_tokens = merged.get("max_tokens")
        if max_tokens is None:
            max_tokens = 4096

        effective_system = self.effective_system_prompt(system_prompt) or ""

        # Separate system messages from conversation messages.
        anthropic_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                if effective_system:
                    effective_system += "\n" + msg.content
                else:
                    effective_system = msg.content
            elif msg.content:
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        yield StreamChunk(event_type="start", agent_id=self.agent_id)

        if not settings.anthropic_api_key:
            yield self._error_chunk(
                error_code="missing_api_key",
                error="Anthropic API key is not configured",
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
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature,
        }
        if effective_system:
            stream_kwargs["system"] = effective_system

        stream_manager, stream, setup_error, attempts = await self._open_stream_with_retries(
            client,
            stream_kwargs,
            resilience,
        )
        if setup_error is not None:
            yield setup_error
            return
        if stream_manager is None or stream is None:
            yield self._error_chunk(
                error_code="upstream_error",
                error="Anthropic stream was not opened",
                attempts=attempts,
                retryable=False,
            )
            return

        stream_closed = False

        async def close_stream_once(exc: BaseException | None = None) -> None:
            nonlocal stream_closed
            if stream_closed:
                return

            stream_closed = True
            if exc is None:
                await stream_manager.__aexit__(None, None, None)
                return

            await stream_manager.__aexit__(
                type(exc),
                exc,
                exc.__traceback__,
            )

        stream_error: BaseException | None = None
        try:
            try:
                async for text in stream.text_stream:
                    for chunk in parser.feed(text):
                        yield chunk
            except Exception as exc:
                stream_error = exc
                for chunk in parser.flush():
                    yield chunk

                error_code = classify_exception(exc, self._provider_error_classes())
                yield self._error_chunk(
                    error_code=error_code,
                    error=safe_error_message(exc),
                    attempts=attempts,
                    retryable=False,
                )
                return

            for chunk in parser.flush():
                yield chunk

            try:
                await close_stream_once()
            except Exception as exc:
                error_code = classify_exception(exc, self._provider_error_classes())
                yield self._error_chunk(
                    error_code=error_code,
                    error=safe_error_message(exc),
                    attempts=attempts,
                    retryable=False,
                )
                return

            total_blocks = parser.block_index + 1 if parser.block_index >= 0 else 0
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=total_blocks,
            )
        finally:
            if not stream_closed:
                try:
                    await close_stream_once(stream_error)
                except Exception as cleanup_exc:
                    _ = cleanup_exc
