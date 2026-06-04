"""Tool-call stream and result payload construction."""

from __future__ import annotations

import json
from typing import Any

from app.agents.orchestrator._internal.tools.types import (
    OrchestratorToolCall,
    OrchestratorToolResult,
)
from app.agents.types import StreamChunk


def _deployment_status_card(result: OrchestratorToolResult) -> dict[str, Any] | None:
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    card = payload.get("status_card")
    if not isinstance(card, dict):
        return None
    if not isinstance(card.get("deployment_id"), str) or not card["deployment_id"]:
        return None
    return card

def _normalize_tool_call(
    chunk: StreamChunk,
    iteration: int,
    call_number: int,
) -> OrchestratorToolCall:
    raw_call_id = chunk.call_id or f"{iteration}.{call_number}"
    call_id = raw_call_id if raw_call_id.startswith("orch.") else f"orch.{iteration}.{call_number}"
    return OrchestratorToolCall(
        call_id=call_id,
        name=chunk.tool_name or "",
        arguments=chunk.tool_arguments or {},
    )

def _tool_call_chunk(call: OrchestratorToolCall) -> StreamChunk:
    return StreamChunk(
        event_type="tool_call",
        agent_id="orchestrator",
        call_id=call.call_id,
        tool_name=call.name,
        tool_arguments=call.arguments,
    )

def _tool_result_chunk(
    call: OrchestratorToolCall,
    result: OrchestratorToolResult,
) -> StreamChunk:
    metadata: dict[str, Any] = {}
    if result.error_code:
        metadata["error_code"] = result.error_code
    if result.needs_user_input:
        metadata["needs_user_input"] = True
    return StreamChunk(
        event_type="tool_result",
        agent_id="orchestrator",
        call_id=call.call_id,
        tool_status="ok" if result.status == "ok" else "error",
        tool_output=result.output,
        tool_output_truncated=result.output_truncated,
        metadata=metadata or None,
    )

def _tool_result_message(
    call: OrchestratorToolCall,
    result: OrchestratorToolResult,
) -> str:
    return f"Tool {call.name} ({call.call_id}) {result.status}: {result.output}"

def _remap_block_index(
    chunk: StreamChunk,
    index_map: dict[int, int],
    next_block_index: int,
) -> tuple[StreamChunk, int]:
    if chunk.block_index is None:
        return chunk, next_block_index
    source_index = chunk.block_index
    if source_index not in index_map:
        index_map[source_index] = next_block_index
        next_block_index += 1
    return chunk.model_copy(update={"block_index": index_map[source_index]}), next_block_index

def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
