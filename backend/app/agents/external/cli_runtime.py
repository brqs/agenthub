"""Shared helpers for local external runtime CLI execution."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

CLI_ENV_ALLOWLIST = {
    "APPDATA",
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
}


@dataclass(frozen=True)
class CliResult:
    return_code: int
    stdout: str
    stderr: str


def cli_env() -> dict[str, str]:
    """Return enough local environment for logged-in CLIs without provider secrets."""
    return {key: value for key, value in os.environ.items() if key in CLI_ENV_ALLOWLIST}


def resolve_command(command: list[str]) -> list[str]:
    if not command:
        return []
    resolved = shutil.which(command[0])
    if resolved:
        return [resolved, *command[1:]]
    return command


async def run_cli_text(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
) -> CliResult:
    process = await asyncio.create_subprocess_exec(
        *resolve_command(command),
        stdin=subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env=cli_env(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return CliResult(
        return_code=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )
