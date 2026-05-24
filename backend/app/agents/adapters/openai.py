"""
OpenAIAdapter — OpenAI / Codex streaming.

TODO(B2):
  - Implement real OpenAI streaming using `openai` SDK.
  - Map choices[0].delta.content → StreamChunk(delta).
  - Handle RateLimitError / APIError.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


class OpenAIAdapter(BaseAgentAdapter):
    """Adapter for OpenAI ChatGPT / Codex models."""

    provider = "openai"

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        # TODO: real implementation
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta="[OpenAIAdapter is a stub — B2 to implement]",
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", total_blocks=1)
