"""Presentation metadata for user-visible Orchestrator blocks."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.agents.types import StreamChunk

EXECUTION_GROUP_ID = "execution-main"

ROLE_EXECUTION_PROCESS = "execution_process"
ROLE_TOOL_TRACE = "tool_trace"
ROLE_EXECUTION_TEXT = "execution_text"
ROLE_ARTIFACT_EVIDENCE = "artifact_evidence"
ROLE_AGENT_SUMMARY = "agent_summary"
ROLE_FINAL_ANSWER = "final_answer"
WORKSPACE_ABSOLUTE_PATH_RE = re.compile(r"/workspaces/[A-Za-z0-9_.-]+")


def presentation(
    role: str,
    *,
    collapsible: bool,
    group_id: str | None = None,
    boundary: str | None = None,
    closes_group_id: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": role,
        "collapsible": collapsible,
    }
    if group_id:
        payload["group_id"] = group_id
    if boundary:
        payload["boundary"] = boundary
    if closes_group_id:
        payload["closes_group_id"] = closes_group_id
    if label:
        payload["label"] = label
    return payload


def execution_process_presentation(*, label: str = "执行过程") -> dict[str, Any]:
    return presentation(
        ROLE_EXECUTION_PROCESS,
        collapsible=True,
        group_id=EXECUTION_GROUP_ID,
        boundary="execution_start",
        label=label,
    )


def tool_trace_presentation() -> dict[str, Any]:
    return presentation(
        ROLE_TOOL_TRACE,
        collapsible=True,
        group_id=EXECUTION_GROUP_ID,
        label="工具调用",
    )


def execution_text_presentation() -> dict[str, Any]:
    return presentation(
        ROLE_EXECUTION_TEXT,
        collapsible=True,
        group_id=EXECUTION_GROUP_ID,
    )


def artifact_evidence_presentation() -> dict[str, Any]:
    return presentation(
        ROLE_ARTIFACT_EVIDENCE,
        collapsible=True,
        group_id=EXECUTION_GROUP_ID,
    )


def agent_summary_presentation() -> dict[str, Any]:
    return presentation(
        ROLE_AGENT_SUMMARY,
        collapsible=False,
        boundary="answer_start",
        closes_group_id=EXECUTION_GROUP_ID,
        label="阶段总结",
    )


def final_answer_presentation() -> dict[str, Any]:
    return presentation(
        ROLE_FINAL_ANSWER,
        collapsible=False,
        boundary="answer_start",
        closes_group_id=EXECUTION_GROUP_ID,
        label="最终回答",
    )


def with_presentation(
    chunk: StreamChunk,
    presentation_payload: Mapping[str, Any] | None,
) -> StreamChunk:
    if not presentation_payload:
        return chunk
    metadata = dict(chunk.metadata or {})
    metadata["presentation"] = dict(presentation_payload)
    return chunk.model_copy(update={"metadata": metadata})


def sanitize_presentation_trace_value(value: Any) -> Any:
    """Remove local-only paths from user-visible process/tool evidence."""
    if isinstance(value, str):
        return WORKSPACE_ABSOLUTE_PATH_RE.sub("workspace", value)
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_presentation_trace_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_presentation_trace_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_presentation_trace_value(item) for item in value]
    return value


def sanitize_presentation_trace_chunk(chunk: StreamChunk) -> StreamChunk:
    updates: dict[str, Any] = {}
    if chunk.tool_arguments is not None:
        updates["tool_arguments"] = sanitize_presentation_trace_value(
            chunk.tool_arguments
        )
    if chunk.tool_output is not None:
        updates["tool_output"] = sanitize_presentation_trace_value(chunk.tool_output)
    if chunk.text_delta is not None:
        updates["text_delta"] = sanitize_presentation_trace_value(chunk.text_delta)
    if chunk.code_delta is not None:
        updates["code_delta"] = sanitize_presentation_trace_value(chunk.code_delta)
    if chunk.metadata is not None:
        updates["metadata"] = sanitize_presentation_trace_value(chunk.metadata)
    if not updates:
        return chunk
    return chunk.model_copy(update=updates)
