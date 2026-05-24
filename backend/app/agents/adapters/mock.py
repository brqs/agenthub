"""
MockAdapter — simulates streaming output for local development.

★ Use this in B1 development before real adapters are ready. ★
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


class MockAdapter(BaseAgentAdapter):
    """Yields a canned response that includes one text block + one code block."""

    provider = "mock"

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        # Echo user's last message to make it obvious we received it
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), "(no input)"
        )

        yield StreamChunk(event_type="start", agent_id=self.agent_id)

        # Block 0: text
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        for piece in [
            "好的，",
            f"我收到了你的消息：「{last_user[:40]}」。\n\n",
            "这是来自 **MockAdapter** 的示例响应：\n\n",
        ]:
            yield StreamChunk(event_type="delta", block_index=0, text_delta=piece)
            await asyncio.sleep(0.05)
        yield StreamChunk(event_type="block_end", block_index=0)

        # Block 1: code
        yield StreamChunk(
            event_type="block_start",
            block_index=1,
            block_type="code",
            metadata={"language": "python"},
        )
        code_lines = [
            "def hello():\n",
            "    print('Hello from MockAdapter!')\n",
            "\n",
            "hello()",
        ]
        for line in code_lines:
            yield StreamChunk(event_type="delta", block_index=1, code_delta=line)
            await asyncio.sleep(0.05)
        yield StreamChunk(event_type="block_end", block_index=1)

        yield StreamChunk(event_type="done", total_blocks=2)
