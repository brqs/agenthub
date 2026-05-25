"""
CustomAdapter — wraps Claude/OpenAI with a user-defined System Prompt.

Delegates to an upstream adapter based on ``config["upstream_provider"]``.
The user's system prompt is injected into the upstream call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.adapters.claude import ClaudeAdapter
from app.agents.adapters.deepseek import DeepSeekAdapter
from app.agents.adapters.openai import OpenAIAdapter
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk

UPSTREAM_ADAPTERS: dict[str, type[BaseAgentAdapter]] = {
    "claude": ClaudeAdapter,
    "deepseek": DeepSeekAdapter,
    "openai": OpenAIAdapter,
}


class CustomAdapter(BaseAgentAdapter):
    """Adapter for user-defined custom agents (System Prompt + upstream model)."""

    provider = "custom"

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)

        upstream_provider = merged.get("upstream_provider")
        if upstream_provider is None or upstream_provider == "":
            upstream_provider = "claude"
        else:
            upstream_provider = str(upstream_provider).lower()

        adapter_cls = UPSTREAM_ADAPTERS.get(upstream_provider)
        if adapter_cls is None:
            yield StreamChunk(event_type="start", agent_id=self.agent_id)
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="unsupported_upstream_provider",
                error=f"Unsupported upstream_provider: {upstream_provider!r}",
            )
            return

        upstream_config = {k: v for k, v in merged.items() if k != "upstream_provider"}
        effective_system = self.effective_system_prompt(system_prompt)

        upstream_adapter = adapter_cls(
            agent_id=self.agent_id,
            system_prompt=effective_system,
            default_config=upstream_config,
        )

        async for chunk in upstream_adapter.stream(
            messages,
            system_prompt=effective_system,
            config=None,
        ):
            yield chunk
