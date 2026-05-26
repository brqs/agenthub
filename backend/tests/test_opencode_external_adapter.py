"""Tests for OpenCode external runtime adapter."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.agents.external.opencode import OpenCodeAdapter
from app.agents.types import ChatMessage, StreamChunk


class FakeStdin:
    def __init__(self) -> None:
        self.data = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class BrokenStdin(FakeStdin):
    def write(self, data: bytes) -> None:
        raise BrokenPipeError("stdin closed")


class FakeStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class HangingStdout:
    async def readline(self) -> bytes:
        await asyncio_never()
        return b""


class FakeStderr:
    def __init__(self, data: bytes = b"") -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class FakeProcess:
    def __init__(
        self,
        lines: list[bytes] | None = None,
        *,
        returncode: int = 0,
        stderr: bytes = b"",
        hang: bool = False,
    ) -> None:
        self.stdin = FakeStdin()
        self.stdout = HangingStdout() if hang else FakeStdout(lines or [])
        self.stderr = FakeStderr(stderr)
        self.returncode: int | None = None
        self._final_returncode = returncode
        self.killed = False

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = -9 if self.killed else self._final_returncode
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class FakeSubprocessFactory:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *argv: str, **kwargs: Any) -> FakeProcess:
        self.calls.append({"argv": list(argv), **kwargs})
        return self.process


async def asyncio_never() -> None:
    await asyncio.Event().wait()


def _json_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload) + "\n").encode()


async def _collect(
    adapter: OpenCodeAdapter,
    workspace_path: Path | None,
    config: dict[str, Any] | None = None,
) -> list[StreamChunk]:
    return [
        chunk
        async for chunk in adapter.stream(
            [ChatMessage(role="user", content="build a page")],
            config=config,
            workspace_path=workspace_path,
        )
    ]


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    process: FakeProcess,
) -> FakeSubprocessFactory:
    factory = FakeSubprocessFactory(process)
    monkeypatch.setattr(
        "app.agents.external.opencode.asyncio.create_subprocess_exec",
        factory,
    )
    return factory


class TestOpenCodeAdapterStream:
    async def test_jsonl_text_stream_completes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [
                _json_line({"type": "text_delta", "text": "hello"}),
                _json_line({"type": "text_delta", "text": " world"}),
                _json_line({"type": "done"}),
            ]
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "delta",
            "block_end",
            "done",
        ]
        assert "".join(chunk.text_delta or "" for chunk in chunks) == "hello world"
        assert chunks[-1].total_blocks == 1

    async def test_tool_call_and_result_are_mapped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [
                _json_line(
                    {
                        "type": "tool_call",
                        "call_id": "c-1",
                        "tool_name": "write_file",
                        "arguments": {"path": "index.html"},
                    }
                ),
                _json_line(
                    {
                        "type": "tool_result",
                        "call_id": "c-1",
                        "status": "ok",
                        "output": "wrote index.html",
                    }
                ),
                _json_line({"type": "done"}),
            ]
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
        tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
        assert tool_call.call_id == "c-1"
        assert tool_call.tool_name == "write_file"
        assert tool_call.tool_arguments == {"path": "index.html"}
        assert tool_result.call_id == "c-1"
        assert tool_result.tool_status == "ok"
        assert tool_result.tool_output == "wrote index.html"

    async def test_workspace_path_is_subprocess_cwd_and_env_is_allowlisted(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
        monkeypatch.setenv("PATH", "fake-path")
        process = FakeProcess([_json_line({"type": "done"})])
        factory = _patch_subprocess(monkeypatch, process)

        await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"command": ["opencode"], "args": ["run", "--jsonl"]},
        )

        call = factory.calls[0]
        assert call["argv"] == ["opencode", "run", "--jsonl"]
        assert call["cwd"] == str(tmp_path)
        assert call["env"]["PATH"] == "fake-path"
        assert "OPENAI_API_KEY" not in call["env"]
        assert process.stdin.closed is True


class TestOpenCodeAdapterErrors:
    async def test_missing_workspace_yields_workspace_violation(self) -> None:
        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), None)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "workspace_violation"

    async def test_nonzero_exit_without_error_event_maps_external_runtime_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([], returncode=2, stderr=b"runtime failed")
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "external_runtime_error"
        assert "runtime failed" in (chunks[-1].error or "")

    async def test_done_then_nonzero_exit_maps_external_runtime_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [_json_line({"type": "done"})],
            returncode=2,
            stderr=b"done but failed",
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "external_runtime_error"
        assert "done but failed" in (chunks[-1].error or "")

    async def test_unsupported_event_is_terminal_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [
                _json_line({"type": "unknown_event"}),
                _json_line({"type": "done"}),
            ]
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert process.killed is True
        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "external_runtime_error"
        assert "unsupported event type" in (chunks[-1].error or "")

    async def test_stdin_failure_yields_external_runtime_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([_json_line({"type": "done"})])
        process.stdin = BrokenStdin()
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert process.killed is True
        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "external_runtime_error"
        assert "stdin closed" in (chunks[-1].error or "")

    async def test_timeout_kills_process_and_yields_timeout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(hang=True)
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"timeout_seconds": 0.01},
        )

        assert process.killed is True
        assert chunks[-1].event_type == "error"
        assert chunks[-1].error_code == "timeout"

    async def test_invalid_jsonl_does_not_leak_full_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        secret_line = b"not-json SECRET_TOKEN_FULL_VALUE\n"
        process = FakeProcess([secret_line])
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert process.killed is True
        assert chunks[-1].event_type == "error"
        assert chunks[-1].error_code == "external_runtime_error"
        assert "SECRET_TOKEN_FULL_VALUE" not in (chunks[-1].error or "")


@pytest.mark.slow
async def test_live_opencode_cli_smoke_is_opt_in(tmp_path: Path) -> None:
    if os.getenv("AGENTHUB_RUN_LIVE_RUNTIME_TESTS") != "1":
        pytest.skip("set AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1 to run live OpenCode CLI smoke")

    command = os.getenv("AGENTHUB_OPENCODE_COMMAND", "opencode")
    command_parts = shlex.split(command, posix=os.name != "nt")
    if not command_parts or shutil.which(command_parts[0]) is None:
        pytest.skip("OpenCode CLI is not installed")

    args = shlex.split(os.getenv("AGENTHUB_OPENCODE_ARGS", ""), posix=os.name != "nt")
    chunks = await _collect(
        OpenCodeAdapter(agent_id="opencode-live"),
        tmp_path,
        config={"command": command_parts, "args": args, "timeout_seconds": 30},
    )

    assert chunks[0].event_type == "start"
    assert chunks[-1].event_type in {"done", "error"}
