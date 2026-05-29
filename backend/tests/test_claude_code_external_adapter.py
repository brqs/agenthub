"""Tests for ClaudeCodeAdapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

import app.agents.external.claude_code as claude_code_module
from app.agents.external.claude_code import ClaudeCodeAdapter
from app.agents.external.cli_runtime import CliCompleted, CliResult
from app.agents.external.direct_chat import DirectChatDecision
from app.agents.types import ChatMessage, StreamChunk


async def _collect(
    adapter: ClaudeCodeAdapter,
    *,
    messages: list[ChatMessage] | None = None,
    workspace_path: Path | None,
    config: dict[str, Any] | None = None,
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


class FakeOptions:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class FakeEventStream:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    async def __aiter__(self) -> AsyncIterator[Any]:
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


class HangingEventStream:
    async def __aiter__(self) -> AsyncIterator[Any]:
        await asyncio.Event().wait()
        yield {"type": "text_delta", "text": "unreachable"}


class FakeSdk:
    ClaudeAgentOptions = FakeOptions

    def __init__(
        self,
        events: list[Any] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.events = events or []
        self.exc = exc
        self.last_prompt = ""
        self.last_options: FakeOptions | None = None

    def query(self, *, prompt: str, options: FakeOptions) -> FakeEventStream:
        self.last_prompt = prompt
        self.last_options = options
        if self.exc:
            raise self.exc
        return FakeEventStream(self.events)


@pytest.fixture
def adapter() -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(agent_id="agent-claude-code")


class TestClaudeCodeAdapterStream:
    async def test_direct_chat_does_not_load_sdk(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fake_direct_chat(**_kwargs: Any) -> DirectChatDecision:
            async def stream() -> AsyncIterator[StreamChunk]:
                yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
                yield StreamChunk(event_type="delta", block_index=0, text_delta="direct")
                yield StreamChunk(event_type="block_end", block_index=0)
                yield StreamChunk(event_type="done", agent_id="agent-claude-code", total_blocks=1)

            return DirectChatDecision(route="direct_chat", stream=stream())

        monkeypatch.setattr(claude_code_module, "maybe_stream_direct_chat", fake_direct_chat)
        monkeypatch.setattr(
            adapter,
            "_load_sdk",
            lambda: pytest.fail("SDK should not load for direct chat"),
        )

        chunks = await _collect(
            adapter,
            workspace_path=tmp_path,
            config={"qa_short_circuit_enabled": True},
            messages=[ChatMessage(role="user", content="Explain timeouts")],
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "direct"

    async def test_text_stream_maps_to_text_block(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(
            events=[
                {"type": "text_delta", "text": "Hello"},
                {"type": "text_delta", "text": " world"},
            ]
        )
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[0].agent_id == "agent-claude-code"
        assert chunks[1].block_type == "text"
        assert chunks[2].text_delta == "Hello"
        assert chunks[3].text_delta == " world"
        assert chunks[-1].total_blocks == 1

    async def test_text_stream_removes_preview_server_commands(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(
            events=[
                {
                    "type": "text_delta",
                    "text": "Created snake.html.\nRun `python3 -m ",
                },
                {"type": "text_delta", "text": "http.server 8082`."},
            ]
        )
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        chunks = await _collect(adapter, workspace_path=tmp_path)
        text = "".join(chunk.text_delta or "" for chunk in chunks)

        assert "Created snake.html" in text
        assert "http.server" not in text
        assert "python3 -m" not in text
        assert "Preview/deploy server commands are handled by AgentHub" in text

    async def test_tool_call_and_result_preserve_call_id(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(
            events=[
                {
                    "type": "tool_call",
                    "call_id": "call-1",
                    "tool_name": "Edit",
                    "tool_arguments": {"file_path": "App.tsx"},
                },
                {
                    "type": "tool_result",
                    "call_id": "call-1",
                    "status": "ok",
                    "output": "updated App.tsx",
                },
            ]
        )
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        chunks = await _collect(adapter, workspace_path=tmp_path)

        tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
        tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")

        assert tool_call.call_id == "call-1"
        assert tool_call.tool_name == "Edit"
        assert tool_call.tool_arguments == {"file_path": "App.tsx"}
        assert tool_result.call_id == "call-1"
        assert tool_result.tool_status == "ok"
        assert tool_result.tool_output == "updated App.tsx"
        assert chunks[-1].total_blocks == 0

    async def test_workspace_path_is_passed_as_sdk_cwd(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        await _collect(adapter, workspace_path=tmp_path)

        assert fake_sdk.last_options is not None
        assert fake_sdk.last_options.kwargs["cwd"] == tmp_path

    async def test_prompt_includes_workspace_rules(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        await _collect(adapter, workspace_path=tmp_path)

        assert str(tmp_path) in fake_sdk.last_prompt
        assert "Workspace root:" in fake_sdk.last_prompt
        assert "Never write to /home/user" in fake_sdk.last_prompt
        assert "Do not run, suggest, or print shell commands" in fake_sdk.last_prompt
        assert "Do not provide terminal commands for port previews" in fake_sdk.last_prompt
        assert "Treat the latest user message as the only active request" in fake_sdk.last_prompt
        assert (
            "answer directly in text and do not inspect files or call tools"
            in fake_sdk.last_prompt
        )
        assert "python3 -m http.server 8082" not in fake_sdk.last_prompt

    async def test_prompt_marks_latest_user_request(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        await _collect(
            adapter,
            messages=[
                ChatMessage(role="user", content="create a snake game"),
                ChatMessage(role="assistant", content="I created snake-game/index.html"),
                ChatMessage(role="user", content="请只总结当前进度"),
            ],
            workspace_path=tmp_path,
        )

        prompt = fake_sdk.last_prompt
        assert "Previous conversation context (not the active task):" in prompt
        assert "Current user request (answer this now):\n请只总结当前进度" in prompt
        assert prompt.index("create a snake game") < prompt.index("Current user request")

    async def test_identity_question_returns_direct_text_without_sdk(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            adapter,
            "_load_sdk",
            lambda: pytest.fail("identity questions must not start Claude Code"),
        )

        chunks = await _collect(
            adapter,
            messages=[
                ChatMessage(role="user", content="create a snake game"),
                ChatMessage(role="assistant", content="I created snake-game/index.html"),
                ChatMessage(role="user", content="你是什么模型"),
            ],
            workspace_path=tmp_path,
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert "我是 Claude Code" in (chunks[2].text_delta or "")
        assert chunks[-1].total_blocks == 1

    async def test_sdk_defaults_to_accept_edits_permission_mode(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        await _collect(adapter, workspace_path=tmp_path)

        assert fake_sdk.last_options is not None
        assert fake_sdk.last_options.kwargs["permission_mode"] == "acceptEdits"

    async def test_sdk_exception_maps_to_external_runtime_error(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(exc=RuntimeError("runtime crashed"))
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "external_runtime_error"
        assert "runtime crashed" in (chunks[1].error or "")

    async def test_sdk_wait_emits_heartbeat_before_hard_timeout(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        class HangingSdk(FakeSdk):
            def query(self, *, prompt: str, options: FakeOptions) -> HangingEventStream:
                self.last_prompt = prompt
                self.last_options = options
                return HangingEventStream()

        monkeypatch.setattr(adapter, "_load_sdk", lambda: HangingSdk())

        chunks = await _collect(
            adapter,
            workspace_path=tmp_path,
            messages=[ChatMessage(role="user", content="wait")],
            config={
                "max_runtime_seconds": 0.3,
                "idle_timeout_seconds": 0.3,
                "heartbeat_interval_seconds": 0.1,
            },
        )

        assert any(chunk.event_type == "heartbeat" for chunk in chunks)
        assert chunks[-1].event_type == "error"
        assert chunks[-1].error_code == "runtime_hard_timeout"

    async def test_missing_sdk_falls_back_to_logged_in_cli(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def missing_sdk() -> Any:
            raise ModuleNotFoundError(
                "No module named 'claude_agent_sdk'",
                name="claude_agent_sdk",
            )

        async def fake_stream_cli_text(
            command: list[str],
            *,
            cwd: Path,
            budget_config: Any,
            agent_id: str,
            provider: str,
            activity_paths: list[Path] | None = None,
        ) -> AsyncIterator[StreamChunk | CliCompleted]:
            _ = command, cwd, budget_config, agent_id, provider, activity_paths
            yield CliCompleted(CliResult(return_code=0, stdout="cli ok\n", stderr=""))

        monkeypatch.setattr(adapter, "_load_sdk", missing_sdk)
        monkeypatch.setattr(claude_code_module, "stream_cli_text", fake_stream_cli_text)

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "cli ok"

    async def test_missing_workspace_path_does_not_load_sdk(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fail_load_sdk() -> Any:
            raise AssertionError("SDK should not load without workspace_path")

        monkeypatch.setattr(adapter, "_load_sdk", fail_load_sdk)

        chunks = await _collect(adapter, workspace_path=None)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "workspace_violation"
        assert chunks[1].error == "workspace_path is required"

    async def test_cli_command_can_be_overridden(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def missing_sdk() -> Any:
            raise ModuleNotFoundError(
                "No module named 'claude_agent_sdk'",
                name="claude_agent_sdk",
            )

        seen_command: list[str] = []

        async def fake_stream_cli_text(
            command: list[str],
            *,
            cwd: Path,
            budget_config: Any,
            agent_id: str,
            provider: str,
            activity_paths: list[Path] | None = None,
        ) -> AsyncIterator[StreamChunk | CliCompleted]:
            _ = cwd, budget_config, agent_id, provider, activity_paths
            seen_command.extend(command)
            yield CliCompleted(CliResult(return_code=0, stdout="cli ok\n", stderr=""))

        monkeypatch.setattr(adapter, "_load_sdk", missing_sdk)
        monkeypatch.setattr(claude_code_module, "stream_cli_text", fake_stream_cli_text)

        chunks = await _collect(
            adapter,
            workspace_path=tmp_path,
            config={"command": ["C:\\Users\\qq\\.local\\bin\\claude.exe"]},
        )

        assert chunks[-1].event_type == "done"
        assert seen_command[0] == "C:\\Users\\qq\\.local\\bin\\claude.exe"
