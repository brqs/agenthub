"""Compatibility shim for the legacy top-level OpenAI adapter."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from pathlib import Path
from typing import Any, cast

import openai

from app.agents.base import BaseAgentAdapter
from app.agents.model_gateway.openai import OpenAIBackend
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.config import settings


class OpenAIAdapter(OpenAIBackend, BaseAgentAdapter):
    """Legacy adapter delegating raw LLM behavior to ModelGateway backend."""

    provider = "openai"
    default_model = "gpt-4o"
    api_key_setting = "openai_api_key"
    base_url_setting = "openai_base_url"
    display_name = "OpenAI"

    def _settings(self) -> Any:
        return settings

    def _openai_module(self) -> Any:
        return openai

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
            OpenAIBackend.stream(
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
