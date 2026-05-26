"""Provider-neutral entry point for raw model backends."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.model_gateway.claude import ClaudeBackend
from app.agents.model_gateway.deepseek import DeepSeekBackend
from app.agents.model_gateway.openai import OpenAIBackend
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

BackendClass = type[ClaudeBackend | OpenAIBackend | DeepSeekBackend]

BACKEND_MAP: dict[str, BackendClass] = {
    "claude": ClaudeBackend,
    "openai": OpenAIBackend,
    "deepseek": DeepSeekBackend,
}


class ModelGateway:
    """Provider-neutral model call entry point for BuiltinAgent."""

    def __init__(
        self,
        backend: str,
        default_config: dict[str, Any] | None = None,
        *,
        agent_id: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        backend_name = backend.lower()
        backend_cls = BACKEND_MAP.get(backend_name)
        if backend_cls is None:
            raise ValueError(f"Unsupported model backend: {backend!r}")

        self.backend_name = backend_name
        self.backend = backend_cls(
            agent_id=agent_id or f"model-gateway-{backend_name}",
            system_prompt=system_prompt,
            default_config=default_config,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        async for chunk in self.backend.stream(
            messages,
            system_prompt=system_prompt,
            config=config,
            tools=tools,
        ):
            yield chunk
