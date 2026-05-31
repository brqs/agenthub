"""Shared helpers for local external runtime CLI execution."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import subprocess
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.external.runtime_budget import (
    RuntimeBudget,
    RuntimeBudgetConfig,
    RuntimeTimeoutError,
)
from app.agents.types import StreamChunk

MAX_CAPTURE_BYTES = 1_000_000

CLI_ENV_ALLOWLIST = {
    "APPDATA",
    "COMSPEC",
    "CODEX_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
}


@dataclass(frozen=True)
class CliResult:
    return_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CliCompleted:
    result: CliResult


class _LimitedBuffer:
    def __init__(self, limit: int = MAX_CAPTURE_BYTES) -> None:
        self.limit = limit
        self.size = 0
        self.chunks: list[bytes] = []
        self.truncated = False

    def append(self, data: bytes) -> None:
        if not data:
            return
        remaining = self.limit - self.size
        if remaining <= 0:
            self.truncated = True
            return
        self.chunks.append(data[:remaining])
        self.size += min(len(data), remaining)
        if len(data) > remaining:
            self.truncated = True

    def text(self) -> str:
        text = b"".join(self.chunks).decode(errors="replace")
        if self.truncated:
            return f"{text}\n...[truncated]"
        return text


def cli_env() -> dict[str, str]:
    """Return enough local environment for logged-in CLIs without provider secrets."""
    env = {key: value for key, value in os.environ.items() if key in CLI_ENV_ALLOWLIST}
    env["PATH"] = _runtime_path(env.get("PATH", ""))
    return env


def resolve_command(command: list[str]) -> list[str]:
    if not command:
        return []
    resolved = shutil.which(command[0], path=_runtime_path(os.environ.get("PATH", "")))
    if resolved:
        return [resolved, *command[1:]]
    return command


def _runtime_path(path_value: str) -> str:
    entries = [entry for entry in path_value.split(os.pathsep) if entry]
    for extra in _extra_runtime_path_entries():
        if extra and extra not in entries:
            entries.insert(0, extra)
    return os.pathsep.join(entries)


def _extra_runtime_path_entries() -> list[str]:
    entries: list[str] = []
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        entries.append(str(Path(user_profile) / ".local" / "bin"))
    home = os.environ.get("HOME")
    if home:
        entries.append(str(Path(home) / ".local" / "bin"))
    return entries


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
        **process_kwargs(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        kill_process_tree(process)
        await process.wait()
        raise
    return CliResult(
        return_code=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


async def stream_cli_text(
    command: list[str],
    *,
    cwd: Path,
    budget_config: RuntimeBudgetConfig,
    agent_id: str,
    provider: str,
    activity_paths: Iterable[Path] | None = None,
) -> AsyncIterator[StreamChunk | CliCompleted]:
    """Run a CLI process while emitting heartbeats and tracking output activity."""
    budget = RuntimeBudget(budget_config)
    stdout_buffer = _LimitedBuffer()
    stderr_buffer = _LimitedBuffer()
    output_queue: asyncio.Queue[None] = asyncio.Queue()
    reader_tasks: list[asyncio.Task[None]] = []
    wait_task: asyncio.Task[int] | None = None
    process: asyncio.subprocess.Process | None = None
    watched_paths = list(activity_paths or [])
    watched_mtimes = _path_mtimes(watched_paths)

    async def read_pipe(
        pipe: asyncio.StreamReader | None,
        buffer: _LimitedBuffer,
    ) -> None:
        if pipe is None:
            return
        while True:
            data = await pipe.read(4096)
            if not data:
                return
            buffer.append(data)
            await output_queue.put(None)

    try:
        process = await asyncio.create_subprocess_exec(
            *resolve_command(command),
            stdin=subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=cli_env(),
            **process_kwargs(),
        )
        reader_tasks = [
            asyncio.create_task(read_pipe(process.stdout, stdout_buffer)),
            asyncio.create_task(read_pipe(process.stderr, stderr_buffer)),
        ]
        wait_task = asyncio.create_task(process.wait())

        while True:
            get_task = asyncio.create_task(output_queue.get())
            done, _ = await asyncio.wait(
                {get_task, wait_task},
                timeout=budget.next_wait_seconds(),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if get_task in done:
                budget.record_activity()
                budget.check_timeout()
                if wait_task.done() and output_queue.empty():
                    await asyncio.gather(*reader_tasks, return_exceptions=True)
                    yield CliCompleted(
                        CliResult(
                            return_code=process.returncode or 0,
                            stdout=stdout_buffer.text(),
                            stderr=stderr_buffer.text(),
                        )
                    )
                    return
                continue

            get_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await get_task

            if wait_task in done:
                await asyncio.gather(*reader_tasks, return_exceptions=True)
                while not output_queue.empty():
                    output_queue.get_nowait()
                    budget.record_activity()
                yield CliCompleted(
                    CliResult(
                        return_code=process.returncode or 0,
                        stdout=stdout_buffer.text(),
                        stderr=stderr_buffer.text(),
                    )
                )
                return

            current_mtimes = _path_mtimes(watched_paths)
            if current_mtimes != watched_mtimes:
                watched_mtimes = current_mtimes
                budget.record_activity()
                continue

            budget.check_timeout()
            yield budget.heartbeat(agent_id=agent_id, provider=provider)
    except RuntimeTimeoutError as exc:
        if process is not None and process.returncode is None:
            kill_process_tree(process)
            await process.wait()
        raise RuntimeTimeoutError(
            exc.error_code,
            str(exc),
            stdout=stdout_buffer.text(),
            stderr=stderr_buffer.text(),
        ) from exc
    finally:
        if process is not None and process.returncode is None:
            kill_process_tree(process)
            with contextlib.suppress(Exception):
                await process.wait()
        for task in reader_tasks:
            if not task.done():
                task.cancel()
        if reader_tasks:
            await asyncio.gather(*reader_tasks, return_exceptions=True)
        if wait_task is not None and not wait_task.done():
            wait_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wait_task


def kill_process_tree(process: asyncio.subprocess.Process) -> None:
    pid = getattr(process, "pid", None)
    if os.name == "posix" and isinstance(pid, int):
        killpg = getattr(os, "killpg", None)
        sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
        with contextlib.suppress(ProcessLookupError):
            if killpg is not None:
                killpg(pid, sigkill)
                return
    process.kill()


def process_kwargs() -> dict[str, Any]:
    if os.name == "posix":
        return {"start_new_session": True}
    return {}


def _path_mtimes(paths: Iterable[Path]) -> tuple[float | None, ...]:
    mtimes: list[float | None] = []
    for path in paths:
        try:
            mtimes.append(path.stat().st_mtime)
        except FileNotFoundError:
            mtimes.append(None)
    return tuple(mtimes)
