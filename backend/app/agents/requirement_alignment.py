"""Shared requirement-alignment prelude for non-orchestrator agents."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.orchestrator.clarification import maybe_handle_clarification
from app.agents.orchestrator.task_planning import has_task_intent, latest_user_request
from app.agents.types import ChatMessage, StreamChunk


@dataclass(frozen=True)
class RequirementAlignmentPrelude:
    """Result of the lightweight requirement-alignment gate."""

    stream: AsyncIterator[StreamChunk] | None = None
    messages: list[ChatMessage] | None = None
    leading_chunks: tuple[StreamChunk, ...] = ()

    @property
    def handled(self) -> bool:
        return self.stream is not None


async def maybe_handle_single_agent_requirement_alignment(
    *,
    agent_id: str,
    messages: list[ChatMessage],
    config: Mapping[str, Any],
    workspace_path: Path | None = None,
) -> RequirementAlignmentPrelude:
    """Run strict requirement alignment before a single agent starts runtime.

    This path intentionally uses the ModelGateway-backed clarification helper and
    never starts an external CLI/SDK or tool loop. If the user has already
    confirmed the clarification, the helper returns augmented messages plus the
    resolved clarification chunks for the real adapter to stream before runtime.
    """

    if _skip_single_agent_alignment(config, messages):
        return RequirementAlignmentPrelude()

    alignment_config = {
        **dict(config),
        "clarification_agent_id": agent_id,
        "requirement_alignment_title": "需求对齐",
    }
    outcome = await maybe_handle_clarification(
        alignment_config,
        messages,
        0,
        None,
        latest_user_request=latest_user_request,
        has_task_intent=has_task_intent,
        allow_auto_start=True,
    )
    if outcome is None:
        return RequirementAlignmentPrelude()
    if outcome.done:
        return RequirementAlignmentPrelude(
            stream=_iter_terminal_alignment_chunks(outcome.chunks, agent_id)
        )
    return RequirementAlignmentPrelude(
        messages=outcome.continue_messages or messages,
        leading_chunks=tuple(outcome.chunks),
    )


def _skip_single_agent_alignment(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> bool:
    if config.get("tasks") is not None:
        return True
    runtime_context = config.get("runtime_context")
    if isinstance(runtime_context, Mapping) and runtime_context.get("orchestrator_task_id"):
        return True
    latest = latest_user_request(messages).strip()
    return latest.startswith("/")


async def _iter_terminal_alignment_chunks(
    chunks: tuple[StreamChunk, ...],
    agent_id: str,
) -> AsyncIterator[StreamChunk]:
    total_blocks = sum(1 for chunk in chunks if chunk.event_type == "block_start")
    for chunk in chunks:
        yield chunk
    yield StreamChunk(event_type="done", agent_id=agent_id, total_blocks=total_blocks)
