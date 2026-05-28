"""Tests for external CLI runtime helpers."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from app.agents.external.cli_runtime import CliCompleted, run_cli_text, stream_cli_text
from app.agents.external.runtime_budget import RuntimeBudgetConfig, RuntimeTimeoutError
from app.agents.types import StreamChunk

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(os.name != "posix", reason="process group cleanup is POSIX-only")
async def test_run_cli_text_timeout_kills_child_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "child.pid"
    script = (
        "import pathlib, subprocess;"
        "child = subprocess.Popen(['sleep', '30']);"
        f"pathlib.Path({str(marker)!r}).write_text(str(child.pid));"
        "child.wait()"
    )

    with pytest.raises(TimeoutError):
        await run_cli_text(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            timeout_seconds=0.5,
        )

    child_pid = int(marker.read_text(encoding="utf-8"))
    for _ in range(30):
        if not _pid_is_running(child_pid):
            break
        await asyncio.sleep(0.1)
    else:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        pytest.fail(f"child process {child_pid} survived CLI timeout cleanup")


def _pid_is_running(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        stat = stat_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    fields = stat.split()
    if len(fields) >= 3 and fields[2] == "Z":
        return False
    return True


async def test_stream_cli_text_emits_heartbeat_for_silent_process(tmp_path: Path) -> None:
    events = []
    command = [sys.executable, "-c", "import time; time.sleep(1)"]

    async for event in stream_cli_text(
        command,
        cwd=tmp_path,
        budget_config=RuntimeBudgetConfig(
            max_runtime_seconds=2,
            idle_timeout_seconds=2,
            heartbeat_interval_seconds=0.1,
        ),
        agent_id="agent-cli",
        provider="test",
    ):
        events.append(event)
        if isinstance(event, StreamChunk) and event.event_type == "heartbeat":
            break

    heartbeat = next(event for event in events if isinstance(event, StreamChunk))
    assert heartbeat.event_type == "heartbeat"
    assert heartbeat.metadata is not None
    assert heartbeat.metadata["provider"] == "test"
    assert heartbeat.metadata["max_runtime_seconds"] == 2
    assert heartbeat.metadata["idle_timeout_seconds"] == 2


@pytest.mark.skipif(os.name != "posix", reason="process group cleanup is POSIX-only")
async def test_stream_cli_text_idle_timeout_kills_child_process_group(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "child.pid"
    script = (
        "import pathlib, subprocess;"
        "child = subprocess.Popen(['sleep', '30']);"
        f"pathlib.Path({str(marker)!r}).write_text(str(child.pid));"
        "child.wait()"
    )

    with pytest.raises(RuntimeTimeoutError) as exc_info:
        async for _ in stream_cli_text(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            budget_config=RuntimeBudgetConfig(
                max_runtime_seconds=5,
                idle_timeout_seconds=0.3,
                heartbeat_interval_seconds=0.1,
            ),
            agent_id="agent-cli",
            provider="test",
        ):
            pass

    assert exc_info.value.error_code == "runtime_idle_timeout"
    child_pid = int(marker.read_text(encoding="utf-8"))
    for _ in range(30):
        if not _pid_is_running(child_pid):
            break
        await asyncio.sleep(0.1)
    else:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        pytest.fail(f"child process {child_pid} survived CLI idle timeout cleanup")


async def test_stream_cli_text_activity_can_exceed_idle_until_hard_timeout(
    tmp_path: Path,
) -> None:
    script = (
        "import sys, time;"
        "end = time.time() + 2;"
        "\nwhile time.time() < end:"
        "\n    print('tick', flush=True); time.sleep(0.05)"
    )

    with pytest.raises(RuntimeTimeoutError) as exc_info:
        async for _ in stream_cli_text(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            budget_config=RuntimeBudgetConfig(
                max_runtime_seconds=0.4,
                idle_timeout_seconds=0.2,
                heartbeat_interval_seconds=0.1,
            ),
            agent_id="agent-cli",
            provider="test",
        ):
            pass

    assert exc_info.value.error_code == "runtime_hard_timeout"
    assert "tick" in exc_info.value.stdout


async def test_stream_cli_text_normal_completion_returns_result(tmp_path: Path) -> None:
    result = None
    async for event in stream_cli_text(
        [sys.executable, "-c", "print('done')"],
        cwd=tmp_path,
        budget_config=RuntimeBudgetConfig(
            max_runtime_seconds=5,
            idle_timeout_seconds=1,
            heartbeat_interval_seconds=0.1,
        ),
        agent_id="agent-cli",
        provider="test",
    ):
        if isinstance(event, CliCompleted):
            result = event.result

    assert result is not None
    assert result.return_code == 0
    assert result.stdout.strip() == "done"
