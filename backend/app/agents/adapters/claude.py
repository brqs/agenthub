"""
ClaudeAdapter — Anthropic streaming.

Uses `anthropic.AsyncAnthropic` to stream text deltas, feeds them into
`StreamingArtifactParser` to split text vs code blocks, and yields standard
`StreamChunk` events for B1 SSE consumption.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

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

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)
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
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="missing_api_key",
                error="Anthropic API key is not configured",
            )
            return

        client = self._create_client()
        parser = StreamingArtifactParser()

        stream_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature,
        }
        if effective_system:
            stream_kwargs["system"] = effective_system

        try:
            async with client.messages.stream(**stream_kwargs) as stream:
                async for text in stream.text_stream:
                    for chunk in parser.feed(text):
                        yield chunk

            for chunk in parser.flush():
                yield chunk

            total_blocks = parser.block_index + 1 if parser.block_index >= 0 else 0
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=total_blocks,
            )
        except anthropic.RateLimitError as exc:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="rate_limit",
                error=str(exc),
            )
        except anthropic.APIError as exc:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="upstream_error",
                error=str(exc),
            )
