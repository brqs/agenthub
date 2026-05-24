"""
ClaudeAdapter — Anthropic streaming.

TODO(B2):
  - Implement real Anthropic streaming using `anthropic` SDK.
  - Integrate `StreamingArtifactParser` to split text vs code blocks.
  - Handle RateLimitError / APIError → yield StreamChunk(error).

Reference: docs/tech-architecture.md § 6.3
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


class ClaudeAdapter(BaseAgentAdapter):
    """Adapter for Anthropic Claude models."""

    provider = "claude"

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
            text_delta="[ClaudeAdapter is a stub — B2 to implement]",
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", total_blocks=1)
