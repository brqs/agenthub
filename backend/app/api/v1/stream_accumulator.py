"""Stream content accumulation for SSE persistence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from importlib import import_module
from typing import Any

from app.agents.types import StreamChunk

TOOL_PREVIEW_MAX_CHARS = 2048


class StreamContentAccumulator:
    """Accumulates streaming chunks into final ContentBlock list for DB persistence."""

    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.process_blocks: dict[int, dict[str, Any]] = {}
        self.pending_tool_calls: dict[str, dict[str, Any]] = {}
        self.has_orphaned_tool_call = False

    @staticmethod
    def _parse_diff(raw: str) -> tuple[str, str, str]:
        """Extract (filename, before, after) from unified diff text."""
        lines = raw.splitlines(keepends=True)
        filename = "changes.diff"
        before_lines: list[str] = []
        after_lines: list[str] = []

        for line in lines:
            stripped = line.rstrip("\n")
            if stripped.startswith("+++ b/"):
                filename = stripped[6:]
            elif stripped.startswith("diff --git "):
                parts = stripped.split()
                if len(parts) >= 4 and parts[2].startswith("a/") and parts[3].startswith("b/"):
                    filename = parts[3][2:]

            if stripped.startswith("diff --git") or stripped.startswith("index "):
                continue
            if stripped.startswith("---") or stripped.startswith("+++"):
                continue
            if stripped.startswith("@@"):
                continue

            if stripped.startswith("-"):
                before_lines.append(stripped[1:])
            elif stripped.startswith("+"):
                after_lines.append(stripped[1:])
            else:
                before_lines.append(stripped)
                after_lines.append(stripped)

        return filename, "\n".join(before_lines), "\n".join(after_lines)

    def _finalize_current(self) -> None:
        """Convert the current accumulating block into a persistable dict."""
        if self.current is None:
            return
        if self.current.get("type") == "diff":
            agent_id = self.current.get("agent_id")
            raw_diff = self.current.get("diff", "")
            try:
                filename, before, after = self._parse_diff(raw_diff)
            except Exception:  # noqa: BLE001
                filename = self.current.get("filename", "changes.diff")
                before = raw_diff
                after = ""
            self.current = {
                "type": "diff",
                "filename": filename,
                "before": before,
                "after": after,
            }
            if agent_id:
                self.current["agent_id"] = agent_id
        elif self.current.get("type") == "workflow":
            self.current = _finalize_workflow_block(self.current)
        elif self.current.get("type") == "code":
            upgraded = _maybe_upgrade_code_to_workflow(self.current)
            if upgraded is not None:
                self.current = upgraded
        elif self.current.get("type") == "text":
            text_block = self.current
            workflow = _maybe_extract_workflow_from_text(text_block)
            self.blocks.append(text_block)
            if workflow is not None:
                self.blocks.append(workflow)
            self.current = None
            return
        self.blocks.append(self.current)
        self.current = None

    def feed(self, chunk: StreamChunk) -> StreamChunk | None:
        if chunk.event_type == "block_start":
            self.current = {"type": chunk.block_type or "text"}
            agent_id = _chunk_agent_id(chunk)
            if agent_id:
                self.current["agent_id"] = agent_id
            if chunk.block_type == "text":
                self.current["text"] = ""
            elif chunk.block_type == "code":
                self.current["code"] = ""
                self.current["language"] = (chunk.metadata or {}).get("language", "text")
            elif chunk.block_type == "diff":
                self.current["diff"] = ""
                self.current["filename"] = (chunk.metadata or {}).get("filename", "changes.diff")
            elif chunk.block_type == "workflow":
                meta = chunk.metadata or {}
                self.current["raw_definition"] = ""
                self.current["format"] = str(meta.get("format", "yaml"))
                for key in (
                    "path",
                    "name",
                    "validation_status",
                    "runtime_status",
                    "dry_run_status",
                    "health_status",
                ):
                    if key in meta:
                        self.current[key] = meta[key]
            elif chunk.block_type == "web_preview":
                meta = chunk.metadata or {}
                self.current["url"] = meta.get("url", "")
                if "title" in meta:
                    self.current["title"] = meta["title"]
                if "description" in meta:
                    self.current["description"] = meta["description"]
                if "thumbnail_url" in meta:
                    self.current["thumbnail_url"] = meta["thumbnail_url"]
            elif chunk.block_type == "file":
                meta = chunk.metadata or {}
                self.current.update(
                    {
                        "filename": str(meta.get("filename") or meta.get("path") or "artifact"),
                        "url": str(meta.get("url") or ""),
                        "size": int(meta.get("size") or 0),
                        "mime_type": str(meta.get("mime_type") or "application/octet-stream"),
                        "artifact_kind": str(meta.get("artifact_kind") or "other"),
                    }
                )
                for key in (
                    "path",
                    "preview_text",
                    "preview_truncated",
                    "metadata",
                ):
                    if key in meta:
                        self.current[key] = meta[key]
            elif chunk.block_type == "deployment_status":
                meta = chunk.metadata or {}
                self.current.update(
                    {
                        "deployment_id": str(meta.get("deployment_id", "")),
                        "kind": meta.get("kind", "static_site"),
                        "status": meta.get("status", "failed"),
                    }
                )
                for key in (
                    "title",
                    "url",
                    "download_url",
                    "error",
                    "logs_preview",
                    "size_bytes",
                    "artifact_digest",
                    "file_count",
                    "published_at",
                    "stopped_at",
                    "expires_at",
                ):
                    if key in meta:
                        self.current[key] = meta[key]
            elif chunk.block_type == "task_card":
                meta = chunk.metadata or {}
                self.current["title"] = str(meta.get("title") or "Orchestrator 调度计划")
                tasks: list[dict[str, Any]] = []
                for raw_task in meta.get("tasks", []):
                    if not isinstance(raw_task, dict):
                        continue
                    tasks.append(
                        {
                            "id": str(raw_task.get("id") or ""),
                            "agent_id": str(raw_task.get("agent_id") or ""),
                            "title": str(raw_task.get("title") or ""),
                            "status": _task_status(raw_task.get("status")),
                        }
                    )
                self.current["tasks"] = tasks
            elif chunk.block_type == "process":
                meta = chunk.metadata or {}
                block = {"type": "process"}
                agent_id = _chunk_agent_id(chunk)
                if agent_id:
                    block["agent_id"] = agent_id
                block.update(_process_block_from_metadata(meta))
                self.blocks.append(block)
                if chunk.block_index is not None:
                    self.process_blocks[chunk.block_index] = block
                self.current = None
            elif chunk.block_type == "clarification":
                meta = chunk.metadata or {}
                self.current.update(_clarification_block_from_metadata(meta))
        elif chunk.event_type == "delta" and self.current is not None:
            if self.current.get("type") == "process":
                return None
            if chunk.text_delta:
                if self.current.get("type") == "diff":
                    self.current["diff"] = self.current.get("diff", "") + chunk.text_delta
                elif self.current.get("type") == "workflow":
                    self.current["raw_definition"] = (
                        self.current.get("raw_definition", "") + chunk.text_delta
                    )
                else:
                    self.current["text"] = self.current.get("text", "") + chunk.text_delta
            if chunk.code_delta:
                if self.current.get("type") == "workflow":
                    self.current["raw_definition"] = (
                        self.current.get("raw_definition", "") + chunk.code_delta
                    )
                else:
                    self.current["code"] = self.current.get("code", "") + chunk.code_delta
        elif chunk.event_type == "delta":
            process_index = chunk.block_index if chunk.block_index is not None else -1
            _apply_process_delta(self.process_blocks.get(process_index), chunk.metadata)
        elif chunk.event_type == "block_end" and self.current is not None:
            self._finalize_current()
        elif chunk.event_type == "block_end" and chunk.block_index is not None:
            self.process_blocks.pop(chunk.block_index, None)
        elif chunk.event_type == "tool_call":
            return self._feed_tool_call(chunk)
        elif chunk.event_type == "tool_result":
            return self._feed_tool_result(chunk)
        elif chunk.event_type == "agent_switch":
            self._feed_agent_switch(chunk)
        return None

    def _feed_tool_call(self, chunk: StreamChunk) -> StreamChunk | None:
        self._finalize_current()
        if not chunk.call_id or not chunk.tool_name:
            return _tool_call_orphan_error("tool_call missing call_id or tool_name")
        if chunk.call_id in self.pending_tool_calls:
            return _tool_call_orphan_error(f"duplicate tool_call: {chunk.call_id}")

        block = {
            "type": "tool_call",
            "call_id": chunk.call_id,
            "tool_name": chunk.tool_name,
            "arguments": _preview_jsonish(chunk.tool_arguments or {}),
            "status": "pending",
        }
        agent_id = _chunk_agent_id(chunk)
        if agent_id:
            block["agent_id"] = agent_id
        self.blocks.append(block)
        self.pending_tool_calls[chunk.call_id] = block
        return None

    def _feed_tool_result(self, chunk: StreamChunk) -> StreamChunk | None:
        self._finalize_current()
        if not chunk.call_id or chunk.call_id not in self.pending_tool_calls:
            return _tool_call_orphan_error(
                f"tool_result without matching tool_call: {chunk.call_id or '<missing>'}"
            )

        block = self.pending_tool_calls.pop(chunk.call_id)
        status = chunk.tool_status or "ok"
        block["status"] = status
        if chunk.tool_output is not None:
            output_preview, output_truncated = _preview_text(
                chunk.tool_output,
                already_truncated=bool(chunk.tool_output_truncated),
            )
            block["output_preview"] = output_preview
            block["output_truncated"] = output_truncated
        elif chunk.tool_output_truncated is not None:
            block["output_truncated"] = chunk.tool_output_truncated
        if status == "error":
            block["error_code"] = _tool_result_error_code(chunk)
        return None

    def _feed_agent_switch(self, chunk: StreamChunk) -> None:
        self._finalize_current()
        for block in self.blocks:
            if block.get("type") != "task_card":
                continue
            tasks = block.get("tasks")
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                if task.get("status") == "running":
                    task["status"] = "done"
                if (
                    task.get("status") == "pending"
                    and task.get("agent_id") == chunk.to_agent
                    and (not chunk.task or task.get("title") == chunk.task)
                ):
                    task["status"] = "running"

    def finalize_orphaned_tools(self) -> bool:
        self._finalize_current()
        if not self.pending_tool_calls:
            return False
        for block in self.pending_tool_calls.values():
            block["status"] = "error"
            block["error_code"] = "tool_call_orphan"
        self.pending_tool_calls.clear()
        self.has_orphaned_tool_call = True
        return True

    def finalize_task_cards(self, *, success: bool) -> None:
        self._finalize_current()
        terminal_status = "done" if success else "error"
        for block in self.blocks:
            if block.get("type") != "task_card":
                continue
            tasks = block.get("tasks")
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if isinstance(task, dict) and task.get("status") == "running":
                    task["status"] = terminal_status

    def to_list(self) -> list[dict[str, Any]]:
        self._finalize_current()
        return self.blocks


def _preview_text(
    value: str,
    *,
    already_truncated: bool = False,
) -> tuple[str, bool]:
    if len(value) <= TOOL_PREVIEW_MAX_CHARS:
        return value, already_truncated
    return value[:TOOL_PREVIEW_MAX_CHARS], True


def _chunk_agent_id(chunk: StreamChunk) -> str | None:
    if chunk.agent_id:
        return chunk.agent_id
    value = (chunk.metadata or {}).get("agent_id")
    if isinstance(value, str) and value:
        return value
    return None


def _preview_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        preview, truncated = _preview_text(value)
        if truncated:
            return f"{preview}...[truncated]"
        return preview
    if isinstance(value, dict):
        return {str(key): _preview_jsonish(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_preview_jsonish(item) for item in value]
    return value


def _maybe_upgrade_code_to_workflow(block: dict[str, Any]) -> dict[str, Any] | None:
    language = str(block.get("language") or "").lower()
    if language not in {"json", "yaml", "yml", "workflow", "workflow-json", "workflow-yaml"}:
        return None
    raw = str(block.get("code") or "")
    workflow = _finalize_workflow_block(
        {
            "type": "workflow",
            "agent_id": block.get("agent_id"),
            "format": _workflow_format_from_language(language, raw),
            "raw_definition": raw,
        }
    )
    if workflow.get("validation_status") == "failed" and not _looks_like_workflow_definition(
        workflow.get("definition")
    ):
        return None
    return workflow


WORKFLOW_FENCE_RE = re.compile(
    r"```(?P<language>workflow(?:-ya?ml|-json)?|ya?ml|json)(?:[^\n`]*)\n"
    r"(?P<body>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
WORKFLOW_PATH_RE = re.compile(
    r"(?<![\w./-])(?P<path>[\w./-]*workflow[\w./-]*\.(?:ya?ml|json))",
    re.IGNORECASE,
)


def _maybe_extract_workflow_from_text(block: dict[str, Any]) -> dict[str, Any] | None:
    text = str(block.get("text") or "")
    if "```" not in text:
        return None
    for match in WORKFLOW_FENCE_RE.finditer(text):
        language = match.group("language")
        raw = match.group("body").strip()
        explicit_workflow = language.lower().replace("_", "-").startswith("workflow")
        workflow = _finalize_workflow_block(
            {
                "type": "workflow",
                "agent_id": block.get("agent_id"),
                "format": _workflow_format_from_language(language, raw),
                "path": _workflow_path_from_text(text),
                "raw_definition": raw,
            }
        )
        if workflow.get("validation_status") == "failed" and not (
            explicit_workflow or _looks_like_workflow_definition(workflow.get("definition"))
        ):
            continue
        return workflow
    return None


def _workflow_path_from_text(text: str) -> str | None:
    match = WORKFLOW_PATH_RE.search(text)
    if match is None:
        return None
    return match.group("path")


def _finalize_workflow_block(block: dict[str, Any]) -> dict[str, Any]:
    raw = str(block.get("raw_definition") or "")
    workflow_format = _workflow_format_from_language(str(block.get("format") or ""), raw)
    payload = _parse_workflow_definition(raw, workflow_format)
    validation_status, validation_errors = _validate_workflow_definition(payload)

    output: dict[str, Any] = {
        "type": "workflow",
        "format": workflow_format,
        "definition": payload if isinstance(payload, dict) else {},
        "nodes": _workflow_list(payload, "nodes"),
        "edges": _workflow_list(payload, "edges"),
        "validation_status": validation_status,
        "runtime_status": "ready" if validation_status == "passed" else "invalid",
        "dry_run_status": "not_supported",
        "health_status": "passed" if validation_status == "passed" else "failed",
    }
    for key in ("agent_id", "path"):
        if block.get(key):
            output[key] = block[key]
    name = block.get("name")
    if not isinstance(name, str) or not name:
        name = payload.get("name") if isinstance(payload, Mapping) else None
    if isinstance(name, str) and name:
        output["name"] = name
    if raw:
        output["raw_definition"] = raw
    if validation_errors:
        output["validation_errors"] = validation_errors
    return output


def _workflow_format_from_language(language: str, raw: str) -> str:
    normalized = language.lower().replace("_", "-")
    if normalized in {"json", "workflow-json", "workflow.json"}:
        return "json"
    if normalized in {"yaml", "yml", "workflow", "workflow-yaml", "workflow-yml"}:
        return "yaml"
    stripped = raw.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    return "yaml"


def _parse_workflow_definition(raw: str, workflow_format: str) -> Any:
    try:
        if workflow_format == "json":
            return json.loads(raw)
        yaml = import_module("yaml")
        return yaml.safe_load(raw)
    except Exception:  # noqa: BLE001
        return {}


def _validate_workflow_definition(payload: Any) -> tuple[str, list[str]]:
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return "failed", ["workflow_not_object"]
    for key in ("version", "name", "nodes", "edges"):
        if key not in payload:
            errors.append(f"workflow_missing_{key}")
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    node_ids: set[str] = set()
    if not isinstance(nodes, list) or not nodes:
        errors.append("workflow_nodes_invalid")
    else:
        for index, node in enumerate(nodes):
            if not isinstance(node, Mapping):
                errors.append(f"workflow_node_{index}_not_object")
                continue
            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                errors.append(f"workflow_node_{index}_missing_id")
                continue
            if node_id in node_ids:
                errors.append(f"workflow_duplicate_node_id:{node_id}")
            node_ids.add(node_id)
            if not isinstance(node.get("type"), str) or not str(node.get("type")).strip():
                errors.append(f"workflow_node_missing_type:{node_id}")
    if not isinstance(edges, list):
        errors.append("workflow_edges_invalid")
    else:
        for index, edge in enumerate(edges):
            if not isinstance(edge, Mapping):
                errors.append(f"workflow_edge_{index}_not_object")
                continue
            source = edge.get("source")
            target = edge.get("target")
            if not isinstance(source, str) or source not in node_ids:
                errors.append(f"workflow_dangling_edge_source:{index}")
            if not isinstance(target, str) or target not in node_ids:
                errors.append(f"workflow_dangling_edge_target:{index}")
    return ("failed" if errors else "passed"), errors


def _workflow_list(payload: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get(key), list):
        return []
    return [dict(item) for item in payload[key] if isinstance(item, Mapping)]


def _looks_like_workflow_definition(payload: Any) -> bool:
    return isinstance(payload, Mapping) and any(
        key in payload for key in ("version", "name", "nodes", "edges")
    )


def _task_status(value: object) -> str:
    if value in {"pending", "running", "done", "error"}:
        return str(value)
    return "pending"


def _process_block_from_metadata(meta: Mapping[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {
        "title": str(meta.get("title") or "思考与执行"),
        "status": _process_status(meta.get("status")),
        "default_collapsed": bool(meta.get("default_collapsed", False)),
        "steps": [],
        "metadata": meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {},
    }
    summary = meta.get("summary")
    if isinstance(summary, str):
        block["summary"] = summary
    for raw_step in meta.get("steps", []):
        if not isinstance(raw_step, Mapping):
            continue
        step = {
            "label": str(raw_step.get("label") or ""),
            "kind": _process_step_kind(raw_step.get("kind")),
            "status": _process_step_status(raw_step.get("status")),
        }
        step_id = raw_step.get("id")
        if isinstance(step_id, str) and step_id:
            step["id"] = step_id
        detail = raw_step.get("detail")
        if isinstance(detail, str):
            step["detail"] = detail
        agent_id = raw_step.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            step["agent_id"] = agent_id
        block["steps"].append(step)
    return block


def _clarification_block_from_metadata(meta: Mapping[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {
        "mode": _clarification_mode(meta.get("mode")),
        "title": str(meta.get("title") or "需求澄清"),
        "status": _clarification_status(meta.get("status")),
        "questions": [],
        "metadata": meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {},
    }
    agent_id = meta.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        block["agent_id"] = agent_id
    current_question = _clarification_question(meta.get("current_question"))
    if current_question is not None:
        block["current_question"] = current_question
    for raw_question in meta.get("questions", []):
        question = _clarification_question(raw_question)
        if question is not None:
            block["questions"].append(question)
    summary = meta.get("summary")
    if isinstance(summary, str):
        block["summary"] = summary
    return block


def _clarification_question(raw_question: object) -> dict[str, Any] | None:
    if not isinstance(raw_question, Mapping):
        return None
    question = {
        "id": str(raw_question.get("id") or "question"),
        "question": str(raw_question.get("question") or ""),
        "options": [
            str(option)
            for option in raw_question.get("options", [])
            if isinstance(option, str) and option.strip()
        ],
        "status": _clarification_question_status(raw_question.get("status")),
    }
    for key in ("reason", "recommended_answer", "answer"):
        value = raw_question.get(key)
        if isinstance(value, str):
            question[key] = value
    return question


def _clarification_mode(value: object) -> str:
    if value in {"auto", "grill_me", "grill_with_docs", "setup_matt_pocock_skills"}:
        return str(value)
    return "auto"


def _clarification_status(value: object) -> str:
    if value in {"waiting", "resolved", "cancelled"}:
        return str(value)
    return "waiting"


def _clarification_question_status(value: object) -> str:
    if value in {"pending", "answered", "skipped"}:
        return str(value)
    return "pending"


def _apply_process_delta(
    block: dict[str, Any] | None,
    metadata: Mapping[str, Any] | None,
) -> None:
    if block is None or not isinstance(metadata, Mapping):
        return
    raw_delta = metadata.get("process_delta")
    if not isinstance(raw_delta, Mapping):
        return
    op = raw_delta.get("op")
    if op == "upsert_step":
        raw_step = raw_delta.get("step")
        if not isinstance(raw_step, Mapping):
            return
        step = _process_step_from_mapping(raw_step)
        steps = block.setdefault("steps", [])
        if not isinstance(steps, list):
            block["steps"] = steps = []
        step_id = step.get("id")
        if isinstance(step_id, str) and step_id:
            for index, existing in enumerate(steps):
                if isinstance(existing, dict) and existing.get("id") == step_id:
                    steps[index] = step
                    return
        steps.append(step)
        return
    if op == "set_summary":
        block["status"] = _process_status(raw_delta.get("status"))
        summary = raw_delta.get("summary")
        if isinstance(summary, str):
            block["summary"] = summary


def _process_step_from_mapping(raw_step: Mapping[str, Any]) -> dict[str, Any]:
    step = {
        "label": str(raw_step.get("label") or ""),
        "kind": _process_step_kind(raw_step.get("kind")),
        "status": _process_step_status(raw_step.get("status")),
    }
    step_id = raw_step.get("id")
    if isinstance(step_id, str) and step_id:
        step["id"] = step_id
    detail = raw_step.get("detail")
    if isinstance(detail, str):
        step["detail"] = detail
    agent_id = raw_step.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        step["agent_id"] = agent_id
    return step


def _process_status(value: object) -> str:
    if value in {"running", "done", "partial", "error"}:
        return str(value)
    return "done"


def _process_step_status(value: object) -> str:
    if value in {"done", "running", "error", "skipped"}:
        return str(value)
    return "done"


def _process_step_kind(value: object) -> str:
    allowed = {
        "routing",
        "planning",
        "dispatch",
        "tool",
        "review",
        "evaluation",
        "workflow",
        "deployment",
        "artifact",
        "repair",
        "summary",
    }
    if isinstance(value, str) and value in allowed:
        return value
    return "summary"


def _tool_call_orphan_error(message: str) -> StreamChunk:
    return StreamChunk(event_type="error", error_code="tool_call_orphan", error=message)


def _tool_result_error_code(chunk: StreamChunk) -> str:
    metadata_error_code = (chunk.metadata or {}).get("error_code")
    if isinstance(metadata_error_code, str) and metadata_error_code:
        return metadata_error_code
    return chunk.error_code or "tool_call_failed"
