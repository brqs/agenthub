"""Shared types for the Agent layer — StreamChunk, ChatMessage."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """Normalized message format passed to all adapters."""

    role: Literal["user", "assistant", "system"]
    content: str


StreamEventType = Literal[
    "start",
    "block_start",
    "delta",
    "block_end",
    "done",
    "error",
    "agent_switch",
    "heartbeat",
]

BlockType = Literal["text", "code", "diff", "web_preview"]


class StreamChunk(BaseModel):
    """Normalized streaming event emitted by all adapters."""

    model_config = ConfigDict(extra="forbid")

    event_type: StreamEventType
    block_index: int | None = None
    block_type: BlockType | None = None
    text_delta: str | None = None
    code_delta: str | None = None
    metadata: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    # for agent_switch event
    from_agent: str | None = None
    to_agent: str | None = None
    task: str | None = None
    # for done event
    message_id: str | None = None
    agent_id: str | None = None
    total_blocks: int | None = None

    def to_sse(self) -> dict[str, str]:
        """Convert to {event, data} dict for sse-starlette."""
        return {
            "event": self.event_type,
            "data": self.model_dump_json(exclude_none=True),
        }


class AdapterConfig(BaseModel):
    """Per-call adapter config. Free-form extra fields allowed."""

    model_config = ConfigDict(extra="allow")

    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    extra: dict[str, Any] = Field(default_factory=dict)
