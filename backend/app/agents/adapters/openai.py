"""
OpenAIAdapter — OpenAI / Codex streaming.

Uses `openai.AsyncOpenAI` to stream text deltas, feeds them into
`StreamingArtifactParser` to split text vs code blocks, and yields standard
`StreamChunk` events for B1 SSE consumption.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import openai

from app.agents.artifact_parser import StreamingArtifactParser
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk
from app.core.config import settings


class OpenAIAdapter(BaseAgentAdapter):
    """Adapter for OpenAI ChatGPT / Codex models."""

    provider = "openai"

    def _create_client(self) -> openai.AsyncOpenAI:
        """Build an async OpenAI client from settings."""
        kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return openai.AsyncOpenAI(**kwargs)

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)
        model = merged.get("model") or "gpt-4o"
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

        if not settings.openai_api_key:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="missing_api_key",
                error="OpenAI API key is not configured",
            )
            return

        client = self._create_client()
        parser = StreamingArtifactParser()

        stream_kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            stream = await client.chat.completions.create(**stream_kwargs)
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
        except openai.RateLimitError as exc:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="rate_limit",
                error=str(exc),
            )
        except openai.APIError as exc:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="upstream_error",
                error=str(exc),
            )
