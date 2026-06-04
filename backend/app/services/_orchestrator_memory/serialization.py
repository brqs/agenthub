"""Serialization and truncation helpers for Orchestrator structured memory."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.agents.orchestrator.types import SubTask


def _task_payload(task: SubTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "agent_id": task.agent_id,
        "title": task.title,
        "depends_on": list(task.depends_on),
        "priority": task.priority,
        "expected_output": task.expected_output,
        "include_history": task.include_history,
        "task_type": task.task_type,
        "review_of": list(task.review_of),
        "handoff_reason": task.handoff_reason,
    }


def _truncate_list(values: Iterable[str], *, max_items: int = 50) -> list[str]:
    return [_truncate_text(value, 1000) or "" for value in list(values)[:max_items]]


def _sanitize_json(value: Any, max_text_chars: int) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, max_text_chars)
    if isinstance(value, Mapping):
        return {str(key): _sanitize_json(item, max_text_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item, max_text_chars) for item in value[:100]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _truncate_text(str(value), max_text_chars)


def _truncate_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _truncate_preserving_edges(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 64:
        return text[:max_chars]
    head = max_chars // 2
    tail = max_chars - head - len("\n...[truncated]...\n")
    return f"{text[:head]}\n...[truncated]...\n{text[-tail:]}"


def _single_line(text: str, max_chars: int) -> str:
    return (_truncate_text(" ".join(text.split()), max_chars) or "").strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _format_counter(values: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items())
