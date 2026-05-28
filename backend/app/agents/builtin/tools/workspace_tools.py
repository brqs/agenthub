"""Workspace read/write tools."""

from __future__ import annotations

import asyncio
from pathlib import Path, PureWindowsPath

from app.agents.builtin.tools.exceptions import ToolExecutionError, WorkspaceViolation
from app.core.config import settings

FORBIDDEN_PARTS = {".agenthub", ".git", ".env", ".ssh", "secrets"}


async def read_file(workspace_root: Path, user_path: str) -> str:
    path = _validate_read_path(workspace_root, user_path)
    return await asyncio.to_thread(_read_text_file, path)


async def write_file(workspace_root: Path, user_path: str, content: str) -> str:
    path = _validate_write_path(workspace_root, user_path)
    encoded = content.encode("utf-8")
    if len(encoded) > settings.workspace_max_read_bytes:
        raise ToolExecutionError("file content exceeds 1 MB")
    await asyncio.to_thread(_write_text_file, path, content)
    return f"wrote {user_path} ({len(encoded)} bytes)"


def _validate_read_path(workspace_root: Path, user_path: str) -> Path:
    candidate = _resolve_workspace_path(workspace_root, user_path)
    if not candidate.exists() or not candidate.is_file():
        raise ToolExecutionError(f"file not found: {user_path}")
    if candidate.stat().st_size > settings.workspace_max_read_bytes:
        raise ToolExecutionError("file exceeds 1 MB")
    return candidate


def _validate_write_path(workspace_root: Path, user_path: str) -> Path:
    candidate = _resolve_workspace_path(workspace_root, user_path)
    if candidate.exists() and candidate.is_dir():
        raise WorkspaceViolation(f"cannot write to directory: {user_path}")
    return candidate


def _resolve_workspace_path(workspace_root: Path, user_path: str) -> Path:
    if not user_path or not user_path.strip():
        raise WorkspaceViolation("workspace path is empty")
    normalized_user_path = user_path.replace("\\", "/").strip()
    workspace = workspace_root.resolve()
    normalized_user_path = _normalize_workspace_path_alias(
        workspace,
        normalized_user_path,
        user_path,
    )
    raw_path = Path(normalized_user_path)
    if raw_path.is_absolute() or PureWindowsPath(normalized_user_path).is_absolute():
        raise WorkspaceViolation(f"absolute path is not allowed: {user_path}")
    if PureWindowsPath(user_path).drive:
        raise WorkspaceViolation(f"drive path is not allowed: {user_path}")

    parts = [part for part in raw_path.parts if part not in {"", ".", "/"}]
    if any(part == ".." for part in parts):
        raise WorkspaceViolation(f"path traversal is not allowed: {user_path}")
    if any(part in FORBIDDEN_PARTS for part in parts):
        raise WorkspaceViolation(f"forbidden path component: {user_path}")

    workspace.mkdir(parents=True, exist_ok=True)
    _reject_symlink_in_existing_path(workspace, parts)
    candidate = (workspace / Path(*parts)).resolve(strict=False)
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise WorkspaceViolation(f"path escapes workspace: {user_path}") from exc
    return candidate


def _normalize_workspace_path_alias(
    workspace: Path,
    normalized_user_path: str,
    original_user_path: str,
) -> str:
    raw_path = Path(normalized_user_path)
    if not raw_path.is_absolute():
        return normalized_user_path

    if PureWindowsPath(original_user_path).drive:
        return normalized_user_path

    absolute_candidate = raw_path.resolve(strict=False)
    try:
        return absolute_candidate.relative_to(workspace).as_posix()
    except ValueError:
        pass

    parts = [part for part in raw_path.parts if part not in {"", ".", "/"}]
    if parts and parts[0] == "workspace":
        alias_parts = parts[1:]
        if not alias_parts:
            raise WorkspaceViolation("workspace path is empty")
        return Path(*alias_parts).as_posix()

    return normalized_user_path


def _reject_symlink_in_existing_path(root: Path, parts: list[str]) -> None:
    current = root
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise WorkspaceViolation(f"symlink path component is not allowed: {part}")


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolExecutionError("file is not valid UTF-8") from exc


def _write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
