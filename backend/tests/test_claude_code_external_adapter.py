"""Tests for ClaudeCodeAdapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

import app.agents.external.claude_code as claude_code_module
from app.agents.external.claude_code import ClaudeCodeAdapter
from app.agents.external.cli_runtime import CliResult
from app.agents.types import ChatMessage, StreamChunk


async def _collect(
    adapter: ClaudeCodeAdapter,
    *,
    messages: list[ChatMessage] | None = None,
    workspace_path: Path | None,
) -> list[StreamChunk]:
    return [
        chunk
        async for chunk in adapter.stream(
            messages or [ChatMessage(role="user", content="build a page")],
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
        assert "Do not start long-running or background servers" in fake_sdk.last_prompt

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

        async def fake_run_cli_text(
            command: list[str],
            *,
            cwd: Path,
            timeout_seconds: float,
        ) -> CliResult:
            _ = command, cwd, timeout_seconds
            return CliResult(return_code=0, stdout="cli ok\n", stderr="")

        monkeypatch.setattr(adapter, "_load_sdk", missing_sdk)
        monkeypatch.setattr(claude_code_module, "run_cli_text", fake_run_cli_text)

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
