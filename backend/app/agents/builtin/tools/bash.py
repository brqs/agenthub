"""Sandboxed bash tool."""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path

from app.agents.builtin.tools.exceptions import ToolExecutionError, WorkspaceViolation

ALLOWED_COMMANDS = {
    "ls",
    "cat",
    "mkdir",
    "rm",
    "mv",
    "cp",
    "cd",
    "pwd",
    "echo",
    "grep",
    "find",
}
FORBIDDEN_TOKENS = {"sudo", "-exec", "-execdir"}
MAX_OUTPUT_CHARS = 4000


async def run_bash(workspace_root: Path, command: str, *, timeout_seconds: float) -> str:
    argv = _parse_command(command)
    executable = argv[0]
    if executable not in ALLOWED_COMMANDS:
        raise ToolExecutionError(f"command is not allowed: {executable}")
    if _has_forbidden_token(argv):
        raise WorkspaceViolation("forbidden bash token")
    if executable == "cd":
        return "cd is a no-op; workspace cwd is fixed"

    workspace = workspace_root.resolve()
    _validate_workspace_args(workspace, argv)
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=workspace,
        env=_safe_env(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise ToolExecutionError("bash command timed out", error_code="timeout") from exc

    output = _decode_output(stdout, stderr)
    if process.returncode != 0:
        raise ToolExecutionError(output or f"command exited with {process.returncode}")
    return output


def _parse_command(command: str) -> list[str]:
    try:
        argv = shlex.split(command, posix=os.name != "nt")
    except ValueError as exc:
        raise ToolExecutionError(f"invalid command: {exc}") from exc
    if not argv:
        raise ToolExecutionError("empty command")
    return argv


def _has_forbidden_token(argv: list[str]) -> bool:
    return any(token in FORBIDDEN_TOKENS or token.startswith("/dev/") for token in argv)


def _validate_workspace_args(workspace: Path, argv: list[str]) -> None:
    for token in argv[1:]:
        if token.startswith("-"):
            continue
        if not _looks_like_path(token):
            continue
        candidate = (workspace / token).resolve()
        try:
            candidate.relative_to(workspace)
        except ValueError as exc:
            raise WorkspaceViolation(f"bash path escapes workspace: {token}") from exc


def _looks_like_path(token: str) -> bool:
    path = Path(token)
    return (
        token in {".", ".."}
        or "/" in token
        or "\\" in token
        or path.is_absolute()
    )


def _safe_env(workspace: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "LANG"):
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["HOME"] = str(workspace)
    return env


def _decode_output(stdout: bytes, stderr: bytes) -> str:
    combined = stdout + stderr
    text = combined.decode("utf-8", errors="replace")
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS]
