"""Compatibility shim for the legacy top-level Claude adapter."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from pathlib import Path
from typing import Any, cast

import anthropic

from app.agents.base import BaseAgentAdapter
from app.agents.model_gateway.claude import ClaudeBackend
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.config import settings


class ClaudeAdapter(ClaudeBackend, BaseAgentAdapter):
    """Legacy adapter delegating raw LLM behavior to ModelGateway backend."""

    provider = "claude"

    def _settings(self) -> Any:
        return settings

    def _anthropic_module(self) -> Any:
        return anthropic

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = workspace_path
        backend_stream = cast(
            AsyncGenerator[StreamChunk, None],
            ClaudeBackend.stream(
                self,
                messages,
                system_prompt=system_prompt,
                config=config,
                tools=tool_specs if tool_specs is not None else tools,
            ),
        )
        async with aclosing(backend_stream) as stream:
            async for chunk in stream:
                yield chunk
