"""
BaseAgentAdapter — the contract between B1 (core) and B2 (agent integration).

★ This is the ONLY interface B1 should use to talk to Agents. ★

Design principles:
  1. Input normalized:  list[ChatMessage]
  2. Output normalized: AsyncIterator[StreamChunk]
  3. Configuration via plain dict (provider-specific keys allowed)
  4. Pure async generator — naturally supports streaming
  5. Adapters MUST NOT access the database directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.agents.types import ChatMessage, StreamChunk


class BaseAgentAdapter(ABC):
    """Abstract base for all Agent adapters."""

    # Subclasses MUST set this class attribute.
    provider: str = ""

    def __init__(
        self,
        agent_id: str,
        system_prompt: str | None = None,
        default_config: dict[str, Any] | None = None,
    ) -> None:
        if not self.provider:
            raise RuntimeError(f"{self.__class__.__name__} must set `provider`")
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.default_config = default_config or {}

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a normalized response.

        Args:
            messages: Conversation history already assembled by ContextBuilder.
            system_prompt: Optional override of `self.system_prompt`.
            config: Optional override of `self.default_config`.

        Yields:
            StreamChunk events (start, block_start, delta, block_end, done, error).

        Implementation note:
            Adapters should ALWAYS yield a `start` first and a `done` (or `error`) last.
        """
        raise NotImplementedError

    def merged_config(self, override: dict[str, Any] | None) -> dict[str, Any]:
        """Helper: shallow-merge default_config with per-call override."""
        return {**self.default_config, **(override or {})}

    def effective_system_prompt(self, override: str | None) -> str | None:
        return override if override is not None else self.system_prompt
