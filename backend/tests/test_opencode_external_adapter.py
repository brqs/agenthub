"""Tests for OpenCode external runtime adapter."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

import app.agents.external.opencode as opencode_module
from app.agents.external.direct_chat import DirectChatDecision
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
        hang_wait: bool = False,
    ) -> None:
        self.stdin = FakeStdin()
        self.stdout = HangingStdout() if hang else FakeStdout(lines or [])
        self.stderr = FakeStderr(stderr)
        self.returncode: int | None = None
        self._final_returncode = returncode
        self._hang_wait = hang_wait
        self.killed = False

    async def wait(self) -> int:
        if self._hang_wait and not self.killed:
            await asyncio_never()
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
    messages: list[ChatMessage] | None = None,
) -> list[StreamChunk]:
    merged_config = {"qa_short_circuit_enabled": False, **(config or {})}
    return [
        chunk
        async for chunk in adapter.stream(
            messages or [ChatMessage(role="user", content="build a page")],
            config=merged_config,
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
    async def test_direct_chat_does_not_start_subprocess(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fake_direct_chat(**_kwargs: Any) -> DirectChatDecision:
            async def stream() -> AsyncIterator[StreamChunk]:
                yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
                yield StreamChunk(event_type="delta", block_index=0, text_delta="direct")
                yield StreamChunk(event_type="block_end", block_index=0)
                yield StreamChunk(event_type="done", agent_id="opencode-test", total_blocks=1)

            return DirectChatDecision(route="direct_chat", stream=stream())

        async def fail_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("OpenCode subprocess should not start for direct chat")

        monkeypatch.setattr(opencode_module, "maybe_stream_direct_chat", fake_direct_chat)
        monkeypatch.setattr(
            opencode_module.asyncio,
            "create_subprocess_exec",
            fail_create_subprocess_exec,
        )

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"qa_short_circuit_enabled": True},
            messages=[ChatMessage(role="user", content="Explain React effects")],
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "direct"

    async def test_simple_greeting_returns_direct_text_without_subprocess_or_classifier(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fail_direct_chat(**_kwargs: Any) -> DirectChatDecision:
            pytest.fail("simple greetings should not start the direct-chat classifier")

        async def fail_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("OpenCode subprocess should not start for simple greetings")

        monkeypatch.setattr(opencode_module, "maybe_stream_direct_chat", fail_direct_chat)
        monkeypatch.setattr(
            opencode_module.asyncio,
            "create_subprocess_exec",
            fail_create_subprocess_exec,
        )

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"qa_short_circuit_enabled": True},
            messages=[ChatMessage(role="user", content="你好")],
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert "OpenCode Helper" in (chunks[2].text_delta or "")

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

    async def test_json_format_text_event_completes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [
                _json_line({"type": "step_start", "part": {"type": "step-start"}}),
                _json_line(
                    {
                        "type": "text",
                        "part": {"type": "text", "text": "hello from opencode"},
                    }
                ),
                _json_line({"type": "step_finish", "part": {"type": "step-finish"}}),
            ]
        )
        factory = _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        argv = factory.calls[0]["argv"]
        assert Path(argv[0]).stem.lower() == "opencode"
        assert argv[1:4] == ["run", "--format", "json"]
        assert "--dir" in argv
        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert "".join(chunk.text_delta or "" for chunk in chunks) == "hello from opencode"

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

    async def test_tool_use_event_is_mapped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [
                _json_line(
                    {
                        "type": "tool_use",
                        "part": {
                            "type": "tool",
                            "id": "tool-1",
                            "tool": "write",
                            "state": {
                                "status": "completed",
                                "input": {"filePath": "index.html"},
                                "output": "wrote index.html",
                            },
                        },
                    }
                ),
                _json_line({"type": "done"}),
            ]
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert chunks[-1].event_type == "done"
        tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
        tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
        assert tool_call.call_id == "tool-1"
        assert tool_call.tool_name == "write"
        assert tool_call.tool_arguments == {"filePath": "index.html"}
        assert tool_result.call_id == "tool-1"
        assert tool_result.tool_status == "ok"
        assert tool_result.tool_output == "wrote index.html"

    @pytest.mark.parametrize("status", ["error", "failed"])
    async def test_tool_use_terminal_error_maps_result(
        self,
        status: str,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [
                _json_line(
                    {
                        "type": "tool_use",
                        "part": {
                            "type": "tool",
                            "id": "tool-1",
                            "tool": "bash",
                            "state": {
                                "status": status,
                                "input": {"command": "python3 -m http.server 8082"},
                                "error": "long-running command rejected",
                            },
                        },
                    }
                ),
                _json_line({"type": "done"}),
            ]
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
        tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
        assert tool_call.call_id == "tool-1"
        assert tool_call.tool_name == "bash"
        assert tool_result.call_id == "tool-1"
        assert tool_result.tool_status == "error"
        assert tool_result.tool_output == "long-running command rejected"

    @pytest.mark.parametrize("status", ["running", "pending", "started", None])
    async def test_tool_use_non_terminal_status_does_not_emit_result(
        self,
        status: str | None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state: dict[str, Any] = {
            "input": {"command": "python3 -m http.server 8082"},
        }
        if status is not None:
            state["status"] = status
        process = FakeProcess(
            [
                _json_line(
                    {
                        "type": "tool_use",
                        "part": {
                            "type": "tool",
                            "id": "tool-1",
                            "tool": "bash",
                            "state": state,
                        },
                    }
                ),
                _json_line({"type": "done"}),
            ]
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert chunks[-1].event_type == "done"
        assert [chunk.event_type for chunk in chunks].count("tool_call") == 1
        assert not any(chunk.event_type == "tool_result" for chunk in chunks)

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
        assert call["env"]["PATH"].endswith("fake-path")
        assert ".local" in call["env"]["PATH"]
        assert "OPENAI_API_KEY" not in call["env"]
        assert process.stdin.closed is True

    async def test_default_prompt_includes_workspace_rules(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([_json_line({"type": "done"})])
        factory = _patch_subprocess(monkeypatch, process)

        await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        prompt = factory.calls[0]["argv"][-1]
        assert str(tmp_path) in prompt
        assert "Workspace root:" in prompt
        assert "Never write to /home/user" in prompt
        assert "Do not run, suggest, or print shell commands" in prompt
        assert "Do not provide terminal commands for port previews" in prompt
        assert "do not create a Node/Express" in prompt
        assert "server.js" in prompt
        assert "Treat the latest user message as the only active request" in prompt
        assert "python3 -m http.server 8082" not in prompt

    async def test_stdin_payload_includes_workspace_rules(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([_json_line({"type": "done"})])
        _patch_subprocess(monkeypatch, process)

        await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"args": ["run", "--jsonl"]},
        )

        payload = json.loads(process.stdin.data.decode())
        assert str(tmp_path) in payload["system_prompt"]
        assert "Workspace root:" in payload["system_prompt"]
        assert "Never write to /home/user" in payload["system_prompt"]
        assert "Do not provide terminal commands for port previews" in payload["system_prompt"]
        assert "do not create a Node/Express" in payload["system_prompt"]
        assert "server.js" in payload["system_prompt"]
        assert "Treat the latest user message as the only active request" in payload[
            "system_prompt"
        ]
        assert "python3 -m http.server 8082" not in payload["system_prompt"]

    async def test_prompt_marks_latest_user_request(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([_json_line({"type": "done"})])
        factory = _patch_subprocess(monkeypatch, process)

        await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            messages=[
                ChatMessage(role="user", content="create a snake game"),
                ChatMessage(role="assistant", content="I created snake-game/index.html"),
                ChatMessage(role="user", content="请只总结当前进度"),
            ],
        )

        prompt = factory.calls[0]["argv"][-1]
        assert "Previous conversation context (not the active task):" in prompt
        assert "Current user request (answer this now):\n请只总结当前进度" in prompt
        assert prompt.index("create a snake game") < prompt.index("Current user request")

    async def test_identity_question_returns_direct_text_without_process(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fail_create_subprocess_exec(*args: Any, **kwargs: Any) -> Any:
            _ = args, kwargs
            raise AssertionError("identity questions must not start OpenCode")

        monkeypatch.setattr(
            asyncio,
            "create_subprocess_exec",
            fail_create_subprocess_exec,
        )

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            messages=[
                ChatMessage(role="user", content="create a snake game"),
                ChatMessage(role="assistant", content="I created snake-game/index.html"),
                ChatMessage(role="user", content="你是什么模型"),
            ],
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert "我是 OpenCode Helper" in (chunks[2].text_delta or "")
        assert chunks[-1].total_blocks == 1


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

    async def test_done_then_nonzero_exit_completes(
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

        assert [chunk.event_type for chunk in chunks] == ["start", "done"]

    async def test_nonzero_exit_after_tool_events_completes(
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
            ],
            returncode=2,
            stderr=b"non-fatal trailer",
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "tool_call",
            "tool_result",
            "done",
        ]

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

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"args": ["run", "--jsonl"]},
        )

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
        assert chunks[-1].error_code == "runtime_hard_timeout"

    async def test_waiting_for_stdout_emits_heartbeat_and_cancel_cleans_process(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(hang=True)
        _patch_subprocess(monkeypatch, process)

        chunks: list[StreamChunk] = []
        stream = OpenCodeAdapter(agent_id="opencode-test").stream(
            [ChatMessage(role="user", content="build a page")],
            config={
                "max_runtime_seconds": 2,
                "idle_timeout_seconds": 2,
                "heartbeat_interval_seconds": 0.1,
            },
            workspace_path=tmp_path,
        )
        async for chunk in stream:
            chunks.append(chunk)
            if chunk.event_type == "heartbeat":
                break
        await stream.aclose()

        assert any(chunk.event_type == "heartbeat" for chunk in chunks)
        assert process.killed is True

    async def test_done_event_wait_process_hang_uses_idle_timeout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([_json_line({"type": "done"})], hang_wait=True)
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={
                "max_runtime_seconds": 1,
                "idle_timeout_seconds": 0.05,
                "heartbeat_interval_seconds": 0.01,
            },
        )

        assert process.killed is True
        assert chunks[-1].event_type == "error"
        assert chunks[-1].error_code == "runtime_idle_timeout"

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
    assert chunks[-1].event_type == "done"
    assert any(chunk.text_delta for chunk in chunks)
