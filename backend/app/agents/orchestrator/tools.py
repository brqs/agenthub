"""Native tools for the Orchestrator tool-calling loop."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.types import ToolSpec

DEFAULT_TOOL_RESULT_MAX_CHARS = 4000
DEFAULT_TOOL_READ_MAX_BYTES = 65536
SENSITIVE_PATH_PARTS = {".agenthub", ".env", ".git", ".ssh", "secrets"}
MAX_WORKSPACE_ENTRIES = 200


@dataclass(frozen=True, slots=True)
class OrchestratorToolResult:
    status: str
    output: str
    error_code: str | None = None
    output_truncated: bool = False
    needs_user_input: bool = False


def orchestrator_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="dispatch_agent",
            description=(
                "Dispatch a task to one available AgentHub group member and return "
                "its observed result."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "title": {"type": "string"},
                    "instruction": {"type": "string"},
                    "expected_output": {"type": "string"},
                    "include_history": {"type": "boolean"},
                },
                "required": ["agent_id", "title", "instruction"],
            },
        ),
        ToolSpec(
            name="inspect_workspace",
            description="List workspace files and directories with metadata.",
            parameters={
                "type": "object",
                "properties": {
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
                    "path": {"type": "string"},
                },
            },
        ),
        ToolSpec(
            name="read_artifact",
            description="Read a text artifact from the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_bytes": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
        ),
        ToolSpec(
            name="validate_html",
            description="Validate that an HTML artifact contains expected static elements.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "required_title": {"type": "string"},
                    "require_input": {"type": "boolean"},
                    "require_button": {"type": "boolean"},
                    "require_script": {"type": "boolean"},
                    "required_text": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["path"],
            },
        ),
        ToolSpec(
            name="start_workspace_preview",
            description=(
                "Start or reuse a platform-managed static preview for a workspace HTML "
                "artifact. Use this for user preview/deploy/port requests."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "entry_path": {"type": "string"},
                    "mode": {"type": "string", "enum": ["static"], "default": "static"},
                    "requested_port": {"type": "integer", "minimum": 1, "maximum": 65535},
                },
                "required": ["entry_path"],
            },
        ),
        ToolSpec(
            name="verify_web_preview",
            description=(
                "Run browser-level quality verification against the current platform "
                "preview, including desktop/mobile rendering, JS errors, resources, "
                "visible text, screenshots, and basic button interactions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "required_text": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "viewports": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["desktop", "mobile"]},
                    },
                    "click_buttons": {"type": "boolean", "default": True},
                    "max_clicks": {"type": "integer", "minimum": 0, "maximum": 10},
                },
            },
        ),
        ToolSpec(
            name="ask_user",
            description="Stop and ask the user for missing information.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["question"],
            },
        ),
    ]


def available_agent_ids(config: Mapping[str, Any]) -> list[str]:
    ids = _agent_ids_from_available_agents(config.get("available_agents"))
    if ids:
        return ids
    return _agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))


async def execute_workspace_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    workspace_path: Path | None,
    result_max_chars: int,
    read_max_bytes: int,
) -> OrchestratorToolResult:
    if name == "inspect_workspace":
        return _inspect_workspace(
            arguments,
            workspace_path=workspace_path,
            result_max_chars=result_max_chars,
        )
    if name == "read_artifact":
        return _read_artifact(
            arguments,
            workspace_path=workspace_path,
            result_max_chars=result_max_chars,
            read_max_bytes=read_max_bytes,
        )
    if name == "validate_html":
        return _validate_html(
            arguments,
            workspace_path=workspace_path,
            result_max_chars=result_max_chars,
            read_max_bytes=read_max_bytes,
        )
    if name == "ask_user":
        return _ask_user(arguments, result_max_chars=result_max_chars)
    return OrchestratorToolResult(
        status="error",
        output=f"tool is not allowed: {name}",
        error_code="tool_not_allowed",
    )


def _inspect_workspace(
    arguments: dict[str, Any],
    *,
    workspace_path: Path | None,
    result_max_chars: int,
) -> OrchestratorToolResult:
    root = _workspace_root(workspace_path)
    if root is None:
        return _tool_error("workspace_path is required", "workspace_missing")
    max_depth = _bounded_int(arguments.get("max_depth"), default=4, minimum=1, maximum=8)
    resolved = _resolve_workspace_path(root, _optional_str(arguments.get("path"), "."))
    if isinstance(resolved, OrchestratorToolResult):
        return resolved
    if not resolved.exists():
        return _tool_error("workspace path does not exist", "path_not_found")
    if not resolved.is_dir():
        return _tool_error("inspect_workspace path must be a directory", "invalid_path")

    entries: list[dict[str, Any]] = []
    base_depth = len(resolved.relative_to(root).parts)
    for path in sorted(resolved.rglob("*")):
        relative = path.relative_to(root)
        if _is_sensitive_path(relative):
            if path.is_dir():
                continue
            continue
        depth = len(relative.parts) - base_depth
        if depth > max_depth:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(
            {
                "path": relative.as_posix(),
                "type": "dir" if path.is_dir() else "file",
                "size": stat.st_size if path.is_file() else None,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        )
        if len(entries) >= MAX_WORKSPACE_ENTRIES:
            break
    output = _json_output(
        {
            "path": resolved.relative_to(root).as_posix() or ".",
            "max_depth": max_depth,
            "entries": entries,
            "truncated": len(entries) >= MAX_WORKSPACE_ENTRIES,
        },
        result_max_chars,
    )
    return OrchestratorToolResult(status="ok", output=output[0], output_truncated=output[1])


def _read_artifact(
    arguments: dict[str, Any],
    *,
    workspace_path: Path | None,
    result_max_chars: int,
    read_max_bytes: int,
) -> OrchestratorToolResult:
    root = _workspace_root(workspace_path)
    if root is None:
        return _tool_error("workspace_path is required", "workspace_missing")
    path = _required_str(arguments.get("path"), "path")
    if isinstance(path, OrchestratorToolResult):
        return path
    resolved = _resolve_workspace_path(root, path)
    if isinstance(resolved, OrchestratorToolResult):
        return resolved
    if not resolved.exists() or not resolved.is_file():
        return _tool_error("artifact path does not exist", "path_not_found")
    max_bytes = _bounded_int(
        arguments.get("max_bytes"),
        default=read_max_bytes,
        minimum=1,
        maximum=read_max_bytes,
    )
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        return _tool_error(str(exc), "read_failed")
    truncated = len(data) > max_bytes
    data = data[:max_bytes]
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return _tool_error("artifact is not valid UTF-8 text", "unsupported_file")
    output = _json_output(
        {
            "path": resolved.relative_to(root).as_posix(),
            "content": content,
            "truncated": truncated,
        },
        result_max_chars,
    )
    return OrchestratorToolResult(
        status="ok",
        output=output[0],
        output_truncated=output[1] or truncated,
    )


def _validate_html(
    arguments: dict[str, Any],
    *,
    workspace_path: Path | None,
    result_max_chars: int,
    read_max_bytes: int,
) -> OrchestratorToolResult:
    root = _workspace_root(workspace_path)
    if root is None:
        return _tool_error("workspace_path is required", "workspace_missing")
    path = _required_str(arguments.get("path"), "path")
    if isinstance(path, OrchestratorToolResult):
        return path
    resolved = _resolve_workspace_path(root, path)
    if isinstance(resolved, OrchestratorToolResult):
        return resolved
    if not resolved.exists() or not resolved.is_file():
        return _tool_error("HTML path does not exist", "path_not_found")
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        return _tool_error(str(exc), "read_failed")
    if len(data) > read_max_bytes:
        data = data[:read_max_bytes]
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError:
        return _tool_error("HTML artifact is not valid UTF-8 text", "unsupported_file")

    checks: dict[str, bool] = {}
    title = _optional_str(arguments.get("required_title"), "")
    if title:
        checks["required_title"] = title in html
    if arguments.get("require_input") is True:
        checks["input"] = bool(re.search(r"<input\b", html, re.IGNORECASE))
    if arguments.get("require_button") is True:
        checks["button"] = bool(re.search(r"<button\b", html, re.IGNORECASE))
    if arguments.get("require_script") is True:
        checks["script"] = bool(re.search(r"<script\b", html, re.IGNORECASE))
    required_text = arguments.get("required_text")
    if isinstance(required_text, list):
        for index, item in enumerate(required_text):
            if isinstance(item, str) and item:
                checks[f"required_text_{index + 1}"] = item in html
    passed = all(checks.values()) if checks else True
    errors = [name for name, ok in checks.items() if not ok]
    output = _json_output(
        {
            "path": resolved.relative_to(root).as_posix(),
            "passed": passed,
            "checks": checks,
            "errors": errors,
            "note": "Static HTML validation only; browser click behavior is not executed.",
        },
        result_max_chars,
    )
    return OrchestratorToolResult(
        status="ok" if passed else "error",
        output=output[0],
        error_code=None if passed else "validation_failed",
        output_truncated=output[1],
    )


def _ask_user(
    arguments: dict[str, Any],
    *,
    result_max_chars: int,
) -> OrchestratorToolResult:
    question = _required_str(arguments.get("question"), "question")
    if isinstance(question, OrchestratorToolResult):
        return question
    reason = _optional_str(arguments.get("reason"), "")
    output = _json_output(
        {
            "needs_user_input": True,
            "question": question,
            "reason": reason,
        },
        result_max_chars,
    )
    return OrchestratorToolResult(
        status="ok",
        output=output[0],
        output_truncated=output[1],
        needs_user_input=True,
    )


def _workspace_root(workspace_path: Path | None) -> Path | None:
    if workspace_path is None:
        return None
    try:
        return workspace_path.resolve(strict=True)
    except OSError:
        return None


def _resolve_workspace_path(
    workspace_root: Path,
    raw_path: str,
) -> Path | OrchestratorToolResult:
    if not raw_path or raw_path == ".":
        relative = Path(".")
    else:
        relative = Path(raw_path)
    if relative.is_absolute():
        return _tool_error("absolute paths are not allowed", "workspace_violation")
    if _looks_like_drive_path(raw_path):
        return _tool_error("drive paths are not allowed", "workspace_violation")
    if ".." in relative.parts:
        return _tool_error("parent path traversal is not allowed", "workspace_violation")
    if _is_sensitive_path(relative):
        return _tool_error("sensitive paths are not allowed", "workspace_violation")
    try:
        resolved = (workspace_root / relative).resolve(strict=False)
    except OSError as exc:
        return _tool_error(str(exc), "workspace_violation")
    if workspace_root != resolved and workspace_root not in resolved.parents:
        return _tool_error("path escapes workspace", "workspace_violation")
    if resolved.exists():
        try:
            strict_resolved = resolved.resolve(strict=True)
        except OSError as exc:
            return _tool_error(str(exc), "workspace_violation")
        if workspace_root != strict_resolved and workspace_root not in strict_resolved.parents:
            return _tool_error("path escapes workspace", "workspace_violation")
        resolved = strict_resolved
    return resolved


def _is_sensitive_path(path: Path) -> bool:
    for part in path.parts:
        lower = part.lower()
        if lower in SENSITIVE_PATH_PARTS or lower.startswith(".env"):
            return True
    return False


def _looks_like_drive_path(path: str) -> bool:
    return len(path) >= 2 and path[1] == ":" and path[0].isalpha()


def _agent_ids_from_available_agents(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("agent_id", item.get("id"))
        if not isinstance(raw_id, str):
            continue
        agent_id = raw_id.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        ids.append(agent_id)
    return ids


def _agent_id_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        agent_id = item.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        result.append(agent_id)
    return result


def _required_str(value: object, field: str) -> str | OrchestratorToolResult:
    if not isinstance(value, str) or not value.strip():
        return _tool_error(f"{field} must be a non-empty string", "invalid_arguments")
    return value.strip()


def _optional_str(value: object, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        return default
    return value.strip()


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(max(value, minimum), maximum)


def _tool_error(output: str, error_code: str) -> OrchestratorToolResult:
    return OrchestratorToolResult(status="error", output=output, error_code=error_code)


def _json_output(payload: dict[str, Any], max_chars: int) -> tuple[str, bool]:
    output = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(output) <= max_chars:
        return output, False
    return output[:max_chars], True
