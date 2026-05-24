"""
Orchestrator — task decomposition + sub-agent dispatch.

TODO(B2):
  1. Use Claude function calling to decompose user request → list[(agent_id, task)].
  2. Yield a "task planning" block.
  3. Sequentially call sub-adapters via registry.get_adapter().
  4. Remap block_index to avoid collisions.
  5. Emit `agent_switch` events between sub-agents.
  6. Final summary block.

Reference: docs/tech-architecture.md § 6.5
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


class OrchestratorAdapter(BaseAgentAdapter):
    """Master agent that coordinates multiple sub-agents in group chat."""

    provider = "custom"  # Orchestrator runs on Claude under the hood

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        # TODO(B2): real implementation
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta=(
                "[Orchestrator stub — B2 to implement]\n\n"
                "Pretending to decompose: 1) sub-task A → @claude-code, "
                "2) sub-task B → @codex-helper"
            ),
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", total_blocks=1)
