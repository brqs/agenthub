"""
CustomAdapter — wraps Claude/OpenAI with a user-defined System Prompt.

TODO(B2):
  - Decide upstream provider from `config["upstream_provider"]` (default: claude).
  - Delegate to ClaudeAdapter / OpenAIAdapter with the user's system_prompt injected.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


class CustomAdapter(BaseAgentAdapter):
    """Adapter for user-defined custom agents (System Prompt + upstream model)."""

    provider = "custom"

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        # TODO: delegate to upstream adapter
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta="[CustomAdapter is a stub — B2 to implement]",
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", total_blocks=1)
