"""Stream chunk accumulation helpers for task attempts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.execution.summary import (
    truncate_preserving_edges as _truncate_preserving_edges,
)
from app.agents.orchestrator._internal.memory import (
    record_event as _memory_record_event,
)
from app.agents.orchestrator.artifacts import (
    extract_artifact_paths_from_mapping as _extract_artifact_paths_from_mapping,
)
from app.agents.orchestrator.artifacts import (
    extract_artifact_paths_from_text as _extract_artifact_paths_from_text,
)
from app.agents.orchestrator.types import (
    DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    OrchestratorRunContext,
    TaskAttempt,
)
from app.agents.orchestrator.workspace_changes import refresh_workspace_conflicts
from app.agents.types import StreamChunk

ARTIFACT_OUTPUT_TOOL_NAMES = {
    "edit",
    "multi_edit",
    "replace",
    "write",
    "write_file",
}


def accumulate_text_event(attempt: TaskAttempt, chunk: StreamChunk) -> None:
    if chunk.text_delta:
        attempt.text_preview = append_limited(
            attempt.text_preview,
            chunk.text_delta,
            DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
        )
    if chunk.code_delta:
        attempt.text_preview = append_limited(
            attempt.text_preview,
            chunk.code_delta,
            DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
        )
    if chunk.metadata:
        attempt.artifact_paths.extend(_extract_artifact_paths_from_mapping(chunk.metadata))


def accumulate_tool_event(attempt: TaskAttempt, chunk: StreamChunk) -> None:
    if chunk.event_type == "tool_call":
        summary = tool_call_summary(chunk)
        if summary:
            attempt.tool_summaries.append(summary)
        if chunk.tool_arguments and is_artifact_output_tool(chunk.tool_name):
            attempt.artifact_paths.extend(
                _extract_artifact_paths_from_mapping(chunk.tool_arguments)
            )
    elif chunk.event_type == "tool_result":
        summary = tool_result_summary(chunk)
        if summary:
            attempt.tool_summaries.append(summary)
        if chunk.tool_output:
            attempt.artifact_paths.extend(
                _extract_artifact_paths_from_text(chunk.tool_output)
            )


def tool_call_summary(chunk: StreamChunk) -> str:
    name = chunk.tool_name or "tool"
    path_bits = []
    if chunk.tool_arguments:
        path_bits = _extract_artifact_paths_from_mapping(chunk.tool_arguments)
    if path_bits:
        return f"{name}({', '.join(path_bits[:3])})"
    return name


def is_artifact_output_tool(tool_name: str | None) -> bool:
    return (tool_name or "").lower() in ARTIFACT_OUTPUT_TOOL_NAMES


def tool_result_summary(chunk: StreamChunk) -> str:
    status = chunk.tool_status or "unknown"
    output = _truncate_preserving_edges(chunk.tool_output or "", 160)
    if output:
        return f"result {status}: {output}"
    return f"result {status}"


def append_limited(existing: str, addition: str, max_chars: int) -> str:
    combined = f"{existing}{addition}"
    return _truncate_preserving_edges(combined, max_chars)


def error_reason(chunk: StreamChunk) -> str:
    return chunk.error or chunk.error_code or "unknown error"


def error_code(exc: ValueError) -> str:
    return str(exc).split(":", maxsplit=1)[0]


def dedupe_strings(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


async def refresh_and_record_workspace_conflicts(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
) -> None:
    conflicts = refresh_workspace_conflicts(run_context)
    for conflict in conflicts:
        path = str(conflict.get("path") or "")
        writers = conflict.get("writers")
        writer_keys = []
        if isinstance(writers, list):
            for writer in writers:
                if not isinstance(writer, dict):
                    continue
                task_id = writer.get("task_id")
                agent_id = writer.get("agent_id")
                if isinstance(task_id, str) and isinstance(agent_id, str):
                    writer_keys.append(f"{task_id}:{agent_id}")
        event_key = f"{path}|{'|'.join(sorted(writer_keys))}"
        if not path or event_key in run_context.workspace_conflict_event_keys:
            continue
        run_context.workspace_conflict_event_keys.add(event_key)
        await _memory_record_event(
            config,
            run_context,
            event_type="workspace_conflict_detected",
            payload=conflict,
        )
