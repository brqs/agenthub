"""Tests for OpenCode external runtime adapter."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import sqlite3
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


def _write_opencode_db_fixture(path: Path, session_id: str) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            """
            create table message (
                id text primary key,
                session_id text not null,
                time_created integer not null,
                data text not null
            )
            """
        )
        db.execute(
            """
            create table part (
                id text primary key,
                message_id text not null,
                session_id text not null,
                time_created integer not null,
                data text not null
            )
            """
        )
        db.execute(
            "insert into message values (?, ?, ?, ?)",
            (
                "msg_user",
                session_id,
                1,
                json.dumps({"role": "user"}, ensure_ascii=False),
            ),
        )
        db.execute(
            "insert into part values (?, ?, ?, ?, ?)",
            (
                "part_user",
                "msg_user",
                session_id,
                2,
                json.dumps({"type": "text", "text": "user prompt"}, ensure_ascii=False),
            ),
        )
        db.execute(
            "insert into message values (?, ?, ?, ?)",
            (
                "msg_assistant",
                session_id,
                3,
                json.dumps({"role": "assistant"}, ensure_ascii=False),
            ),
        )
        db.execute(
            "insert into part values (?, ?, ?, ?, ?)",
            (
                "part_reasoning",
                "msg_assistant",
                session_id,
                4,
                json.dumps(
                    {"type": "reasoning", "text": "hidden reasoning"},
                    ensure_ascii=False,
                ),
            ),
        )
        db.execute(
            "insert into part values (?, ?, ?, ?, ?)",
            (
                "part_text",
                "msg_assistant",
                session_id,
                5,
                json.dumps(
                    {"type": "text", "text": "assistant visible text"},
                    ensure_ascii=False,
                ),
            ),
        )


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


def test_runtime_status_requires_credentials_or_readable_shared_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opencode_module, "_command_available", lambda _command: True)
    monkeypatch.setattr(opencode_module, "_has_provider_credentials", lambda: False)
    monkeypatch.setattr(opencode_module, "_has_shared_auth", lambda: False)

    status, error = opencode_module.opencode_runtime_status({})

    assert status == "unavailable"
    assert error == opencode_module.OPENCODE_MISSING_CREDENTIALS_ERROR


def test_runtime_status_allows_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opencode_module, "_command_available", lambda _command: True)
    monkeypatch.setattr(opencode_module, "_has_provider_credentials", lambda: True)
    monkeypatch.setattr(opencode_module, "_has_shared_auth", lambda: False)

    status, error = opencode_module.opencode_runtime_status({})

    assert status == "ready"
    assert error is None


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
        assert "--model" not in argv
        assert "--dir" in argv
        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert "".join(chunk.text_delta or "" for chunk in chunks) == "hello from opencode"

    async def test_json_format_skips_reasoning_and_hidden_think_tags(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess(
            [
                _json_line({"type": "reasoning", "text": "hidden reasoning"}),
                _json_line(
                    {
                        "type": "text",
                        "part": {
                            "type": "reasoning",
                            "text": "hidden part reasoning",
                        },
                    }
                ),
                _json_line(
                    {
                        "type": "text_delta",
                        "text": "<think>hidden</think>visible</think>",
                    }
                ),
                _json_line({"type": "done"}),
            ]
        )
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        text = "".join(chunk.text_delta or "" for chunk in chunks)
        assert text == "visible"
        assert "hidden" not in text
        assert "<think>" not in text
        assert "</think>" not in text

    async def test_json_format_uses_configured_model(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([_json_line({"type": "done"})])
        factory = _patch_subprocess(monkeypatch, process)

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"model": "deepseek/deepseek-v4-flash"},
        )

        assert chunks[-1].event_type == "done"
        argv = factory.calls[0]["argv"]
        assert argv[4:6] == ["--model", "deepseek/deepseek-v4-flash"]

    async def test_json_format_reads_assistant_text_from_opencode_db_when_stdout_is_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        session_id = "ses_test"
        process = FakeProcess(
            [
                _json_line(
                    {
                        "type": "step_start",
                        "sessionID": session_id,
                        "part": {"type": "step-start"},
                    }
                )
            ]
        )
        _patch_subprocess(monkeypatch, process)
        db_path = tmp_path / "opencode.db"
        _write_opencode_db_fixture(db_path, session_id)

        chunks = await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"opencode_db_path": str(db_path)},
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "assistant visible text"
        assert chunks[-1].total_blocks == 1

    async def test_json_format_skips_unreadable_shared_db_and_reads_home_db(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        session_id = "ses_home"
        process = FakeProcess(
            [
                _json_line(
                    {
                        "type": "step_start",
                        "sessionID": session_id,
                        "part": {"type": "step-start"},
                    }
                )
            ]
        )
        _patch_subprocess(monkeypatch, process)

        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()
        shared_db = shared_dir / "opencode.db"
        shared_db.write_text("not sqlite", encoding="utf-8")
        home = tmp_path / "home"
        home_db = home / ".local" / "share" / "opencode" / "opencode.db"
        home_db.parent.mkdir(parents=True)
        _write_opencode_db_fixture(home_db, session_id)

        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(opencode_module, "_shared_auth_dir", lambda: shared_dir)

        def fake_readable(path: Path) -> bool:
            return path != shared_db and path.is_file()

        monkeypatch.setattr(opencode_module, "_is_readable_file", fake_readable)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert chunks[2].text_delta == "assistant visible text"
        assert chunks[-1].event_type == "done"

    async def test_json_format_reads_assistant_text_from_isolated_runtime_db(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        session_id = "ses_isolated"
        process = FakeProcess(
            [
                _json_line(
                    {
                        "type": "step_start",
                        "sessionID": session_id,
                        "part": {"type": "step-start"},
                    }
                )
            ]
        )
        _patch_subprocess(monkeypatch, process)

        runtime_home = tmp_path / "runtime-home"
        runtime_db = runtime_home / ".local" / "share" / "opencode" / "opencode.db"
        runtime_db.parent.mkdir(parents=True)
        _write_opencode_db_fixture(runtime_db, session_id)

        real_runtime_env = opencode_module.OpenCodeAdapter._runtime_env

        def fake_runtime_env(
            self: OpenCodeAdapter,
            config: dict[str, Any],
            workspace_path: Path,
        ) -> dict[str, str]:
            env = real_runtime_env(self, config, workspace_path)
            env["HOME"] = str(runtime_home)
            env["XDG_DATA_HOME"] = str(runtime_home / ".local" / "share")
            return env

        monkeypatch.setattr(OpenCodeAdapter, "_runtime_env", fake_runtime_env)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert chunks[2].text_delta == "assistant visible text"
        assert chunks[-1].event_type == "done"

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
        monkeypatch.setenv("SECRET_TOKEN_FULL_VALUE", "must-not-leak")
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
        assert call["env"]["OPENAI_API_KEY"] == "secret-key"
        assert "SECRET_TOKEN_FULL_VALUE" not in call["env"]
        assert process.stdin.closed is True

    async def test_shared_auth_removes_generic_provider_env_from_runtime(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
        monkeypatch.setenv("OPENCODE_EXPERIMENT", "enabled")
        source_dir = tmp_path / "opencode-auth"
        source_dir.mkdir()
        (source_dir / "auth.json").write_text('{"auth":"test"}', encoding="utf-8")
        monkeypatch.setattr(opencode_module, "_shared_auth_dir", lambda: source_dir)
        process = FakeProcess([_json_line({"type": "done"})])
        factory = _patch_subprocess(monkeypatch, process)

        await _collect(
            OpenCodeAdapter(agent_id="opencode-test"),
            tmp_path,
            config={"command": ["opencode"], "args": ["run", "--jsonl"]},
        )

        env = factory.calls[0]["env"]
        assert "OPENAI_API_KEY" not in env
        assert "DEEPSEEK_API_KEY" not in env
        assert env["OPENCODE_EXPERIMENT"] == "enabled"

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
        assert "create or update those exact workspace-relative files" in prompt
        assert "Do not replace a requested multi-file artifact" in prompt
        assert "Keep implementation runs bounded" in prompt
        assert "The Current user request above is complete and actionable" in prompt
        assert "If the workspace is empty, create the requested files" in prompt
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

    async def test_missing_cli_yields_actionable_runtime_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def raise_file_not_found(*_args: Any, **_kwargs: Any) -> Any:
            raise FileNotFoundError("opencode")

        monkeypatch.setattr(
            opencode_module.asyncio,
            "create_subprocess_exec",
            raise_file_not_found,
        )

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "external_runtime_error"
        assert "OpenCode CLI command 'opencode' was not found" in (
            chunks[-1].error or ""
        )
        assert "[Errno 2]" not in (chunks[-1].error or "")

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

    async def test_auth_failure_is_normalized(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        process = FakeProcess([], returncode=1, stderr=b"No API key configured")
        _patch_subprocess(monkeypatch, process)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "external_runtime_error"
        assert "no usable model credentials are configured" in (chunks[-1].error or "")

    async def test_shared_auth_copy_permission_error_is_normalized(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "opencode-auth"
        source_dir.mkdir()
        (source_dir / "auth.json").write_text('{"auth":"test"}', encoding="utf-8")
        monkeypatch.setattr(opencode_module, "_has_provider_credentials", lambda: False)
        monkeypatch.setattr(opencode_module, "_shared_auth_dir", lambda: source_dir)

        def raise_permission(_source: Path, _destination: Path) -> None:
            raise PermissionError(
                "[Errno 13] Permission denied: "
                "'/root/.local/share/opencode/auth.json'"
            )

        monkeypatch.setattr(opencode_module.shutil, "copy2", raise_permission)

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[-1].error_code == "external_runtime_error"
        assert "no usable model credentials are configured" in (chunks[-1].error or "")
        assert "/root/.local/share/opencode/auth.json" not in (chunks[-1].error or "")
        assert "[Errno 13]" not in (chunks[-1].error or "")

    async def test_provider_credentials_still_copy_shared_auth_into_isolated_home(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
        empty_home = tmp_path / "empty-home"
        empty_home.mkdir()
        monkeypatch.setenv("HOME", str(empty_home))
        source_dir = tmp_path / "opencode-auth"
        source_dir.mkdir()
        (source_dir / "auth.json").write_text('{"auth":"test"}', encoding="utf-8")
        monkeypatch.setattr(opencode_module, "_shared_auth_dir", lambda: source_dir)

        copied: list[tuple[Path, Path]] = []

        def fake_copy(source: Path, destination: Path) -> None:
            copied.append((source, destination))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

        monkeypatch.setattr(opencode_module.shutil, "copy2", fake_copy)
        _patch_subprocess(monkeypatch, FakeProcess([_json_line({"type": "done"})]))

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "done"]
        assert copied
        assert copied[0][0] == source_dir / "auth.json"
        assert copied[0][1].name == "auth.json"

    async def test_provider_credentials_allow_shared_auth_copy_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
        source_dir = tmp_path / "opencode-auth"
        source_dir.mkdir()
        (source_dir / "auth.json").write_text('{"auth":"test"}', encoding="utf-8")
        monkeypatch.setattr(opencode_module, "_shared_auth_dir", lambda: source_dir)

        def fail_copy(_source: Path, _destination: Path) -> None:
            raise PermissionError("permission denied")

        monkeypatch.setattr(opencode_module.shutil, "copy2", fail_copy)
        _patch_subprocess(monkeypatch, FakeProcess([_json_line({"type": "done"})]))

        chunks = await _collect(OpenCodeAdapter(agent_id="opencode-test"), tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "done"]

    def test_safe_message_normalizes_raw_auth_permission(self) -> None:
        error = OpenCodeAdapter._safe_message(
            PermissionError(
                "[Errno 13] Permission denied: "
                "'/root/.local/share/opencode/auth.json'"
            )
        )

        assert error == opencode_module.OPENCODE_MISSING_CREDENTIALS_ERROR

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
