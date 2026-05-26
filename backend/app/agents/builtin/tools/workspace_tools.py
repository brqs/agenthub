"""Workspace read/write tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.builtin.tools.exceptions import ToolExecutionError, WorkspaceViolation

MAX_FILE_BYTES = 1_000_000
FORBIDDEN_PARTS = {".agenthub", ".git", ".env", ".ssh", "secrets"}


async def read_file(workspace_root: Path, user_path: str) -> str:
    path = _validate_read_path(workspace_root, user_path)
    return await asyncio.to_thread(_read_text_file, path)


async def write_file(workspace_root: Path, user_path: str, content: str) -> str:
    path = _validate_write_path(workspace_root, user_path)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise ToolExecutionError("file content exceeds 1 MB")
    await asyncio.to_thread(_write_text_file, path, content)
    return f"wrote {user_path} ({len(encoded)} bytes)"


def _validate_read_path(workspace_root: Path, user_path: str) -> Path:
    candidate = _resolve_workspace_path(workspace_root, user_path)
    if ".agenthub" in candidate.parts:
        raise WorkspaceViolation("cannot read .agenthub/")
    if not candidate.exists() or not candidate.is_file():
        raise ToolExecutionError(f"file not found: {user_path}")
    if candidate.stat().st_size > MAX_FILE_BYTES:
        raise ToolExecutionError("file exceeds 1 MB")
    return candidate


def _validate_write_path(workspace_root: Path, user_path: str) -> Path:
    candidate = _resolve_workspace_path(workspace_root, user_path)
    if any(part in FORBIDDEN_PARTS for part in candidate.parts):
        raise WorkspaceViolation(f"forbidden path component: {user_path}")
    return candidate


def _resolve_workspace_path(workspace_root: Path, user_path: str) -> Path:
    if not user_path or Path(user_path).is_absolute():
        raise WorkspaceViolation(f"path escapes workspace: {user_path}")
    workspace = workspace_root.resolve()
    candidate = (workspace / user_path).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise WorkspaceViolation(f"path escapes workspace: {user_path}") from exc
    if candidate.is_symlink():
        raise WorkspaceViolation("symlinks not allowed")
    return candidate


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolExecutionError("file is not valid UTF-8") from exc


def _write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
