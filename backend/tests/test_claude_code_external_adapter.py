"""Tests for ClaudeCodeAdapter."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import app.agents.external.claude_code as claude_code_module
import app.agents.external.direct_chat as direct_chat_module
import app.agents.external.runtime_isolation as runtime_isolation_module
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


class HangingModelGateway:
    def __init__(
        self,
        backend: str,
        default_config: dict[str, Any] | None = None,
        *,
        agent_id: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        _ = backend, default_config, system_prompt
        self.agent_id = agent_id

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, tools
        if self.agent_id == "external-direct-chat-classifier":
            yield StreamChunk(
                event_type="delta",
                text_delta='{"route":"direct_chat","confidence":0.99,"reason":"qa"}',
            )
            yield StreamChunk(event_type="done", agent_id=self.agent_id)
            return
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta="partial answer")
        await asyncio.Event().wait()


class HangingClassifierGateway(HangingModelGateway):
    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, tools
        if self.agent_id == "external-direct-chat-classifier":
            await asyncio.Event().wait()
        yield StreamChunk(event_type="delta", text_delta="runtime answer")
        yield StreamChunk(event_type="done", agent_id=self.agent_id)


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

    async def test_direct_chat_timeout_closes_partial_block_and_errors(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(direct_chat_module, "ModelGateway", HangingModelGateway)
        monkeypatch.setattr(
            adapter,
            "_load_sdk",
            lambda: pytest.fail("direct chat timeout must not start Claude Code"),
        )

        chunks = await _collect(
            adapter,
            workspace_path=tmp_path,
            config={
                "qa_short_circuit_enabled": True,
                "qa_stream_idle_timeout_seconds": 0.01,
                "qa_stream_max_runtime_seconds": 0.05,
            },
            messages=[ChatMessage(role="user", content="Explain timeouts")],
        )

        event_types = [chunk.event_type for chunk in chunks]
        assert event_types[:3] == ["start", "block_start", "delta"]
        assert "block_end" in event_types
        assert event_types[-1] == "error"
        assert chunks[2].text_delta == "partial answer"
        assert chunks[-1].error_code == "direct_chat_timeout"

    async def test_direct_chat_classifier_timeout_falls_back_to_runtime(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(direct_chat_module, "ModelGateway", HangingClassifierGateway)
        fake_sdk = FakeSdk(events=[{"type": "text_delta", "text": "runtime path"}])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        chunks = await _collect(
            adapter,
            workspace_path=tmp_path,
            config={
                "qa_short_circuit_enabled": True,
                "qa_stream_idle_timeout_seconds": 0.01,
                "qa_stream_max_runtime_seconds": 0.05,
            },
            messages=[ChatMessage(role="user", content="Explain timeouts")],
        )

        text = "".join(chunk.text_delta or "" for chunk in chunks)
        assert chunks[-1].event_type == "done"
        assert "runtime path" in text
        assert fake_sdk.last_prompt

    async def test_simple_greeting_returns_direct_text_without_sdk_or_classifier(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fail_direct_chat(**_kwargs: Any) -> DirectChatDecision:
            pytest.fail("simple greetings should not start the direct-chat classifier")

        monkeypatch.setattr(claude_code_module, "maybe_stream_direct_chat", fail_direct_chat)
        monkeypatch.setattr(
            adapter,
            "_load_sdk",
            lambda: pytest.fail("simple greetings should not load Claude Code"),
        )

        chunks = await _collect(
            adapter,
            workspace_path=tmp_path,
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
        assert "Claude Code" in (chunks[2].text_delta or "")

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

    async def test_text_stream_removes_node_server_preview_commands(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(
            events=[
                {
                    "type": "text_delta",
                    "text": "Created files.\nRun `node ",
                },
                {"type": "text_delta", "text": "server.js` on port 8082."},
            ]
        )
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        chunks = await _collect(adapter, workspace_path=tmp_path)
        text = "".join(chunk.text_delta or "" for chunk in chunks)

        assert "Created files" in text
        assert "node server.js" not in text
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
        assert "Before overwriting or editing an existing file" in fake_sdk.last_prompt
        assert "Prefer relative paths from the workspace root" in fake_sdk.last_prompt
        assert "Do not run, suggest, or print shell commands" in fake_sdk.last_prompt
        assert "Do not provide terminal commands for port previews" in fake_sdk.last_prompt
        assert "do not create a Node/Express" in fake_sdk.last_prompt
        assert "server.js" in fake_sdk.last_prompt
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

    async def test_sdk_uses_message_scoped_runtime_isolation(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)
        state_dir = tmp_path / "runtime-state"
        monkeypatch.setattr(
            runtime_isolation_module.settings,
            "external_runtime_state_dir",
            str(state_dir),
        )

        await _collect(
            adapter,
            workspace_path=tmp_path / "workspaces" / "conv-a",
            config={
                "runtime_context": {
                    "conversation_id": "conv-a",
                    "agent_message_id": "msg-a",
                    "agent_id": "agent-claude-code",
                }
            },
        )

        assert fake_sdk.last_options is not None
        options = fake_sdk.last_options.kwargs
        assert options["continue_conversation"] is False
        assert options["resume"] is None
        assert str(UUID(options["session_id"])) == options["session_id"]
        assert Path(options["env"]["HOME"]).parts[-3:] == (
            "conv-a",
            "agent-claude-code",
            "msg-a",
        )
        assert Path(options["env"]["XDG_CONFIG_HOME"]).parts[-4:] == (
            "conv-a",
            "agent-claude-code",
            "msg-a",
            ".config",
        )
        assert (Path(options["env"]["HOME"]) / ".claude.json").exists()

    async def test_sdk_uses_agent_message_uuid_as_session_id(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)
        agent_message_id = "8f7fdcef-f533-4744-b751-0c6a09b3c91b"

        await _collect(
            adapter,
            workspace_path=tmp_path,
            config={"runtime_context": {"agent_message_id": agent_message_id}},
        )

        assert fake_sdk.last_options is not None
        assert fake_sdk.last_options.kwargs["session_id"] == agent_message_id

    async def test_sdk_uses_task_scoped_session_for_orchestrator_attempts(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)
        state_dir = tmp_path / "runtime-state"
        monkeypatch.setattr(
            runtime_isolation_module.settings,
            "external_runtime_state_dir",
            str(state_dir),
        )
        agent_message_id = "8f7fdcef-f533-4744-b751-0c6a09b3c91b"

        await _collect(
            adapter,
            workspace_path=tmp_path / "workspaces" / "conv-a",
            config={
                "runtime_context": {
                    "conversation_id": "conv-a",
                    "agent_message_id": agent_message_id,
                    "agent_id": "agent-claude-code",
                    "orchestrator_task_id": "frontend_impl",
                    "orchestrator_attempt_index": "1",
                }
            },
        )

        assert fake_sdk.last_options is not None
        options = fake_sdk.last_options.kwargs
        assert str(UUID(options["session_id"])) == options["session_id"]
        assert options["session_id"] != agent_message_id
        assert Path(options["env"]["HOME"]).parts[-5:] == (
            "conv-a",
            "agent-claude-code",
            agent_message_id,
            "frontend_impl",
            "1",
        )

    async def test_sdk_runtime_home_bootstraps_claude_credentials(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)
        source_home = tmp_path / "source-home"
        source_claude = source_home / ".claude"
        source_claude.mkdir(parents=True)
        (source_home / ".claude.json").write_text(
            '{"hasCompletedOnboarding":true,"auth":"test"}',
            encoding="utf-8",
        )
        (source_claude / "settings.json").write_text('{"theme":"test"}', encoding="utf-8")
        (source_claude / "settings.local.json").write_text(
            '{"permissions":{"allow":["Edit"]}}',
            encoding="utf-8",
        )
        (source_claude / "history.jsonl").write_text("do not copy\n", encoding="utf-8")
        state_dir = tmp_path / "runtime-state"
        monkeypatch.setenv("HOME", str(source_home))
        monkeypatch.setattr(
            runtime_isolation_module.settings,
            "external_runtime_state_dir",
            str(state_dir),
        )

        await _collect(
            adapter,
            workspace_path=tmp_path / "workspaces" / "conv-a",
            config={"runtime_context": {"agent_message_id": "msg-a"}},
        )

        assert fake_sdk.last_options is not None
        runtime_home = Path(fake_sdk.last_options.kwargs["env"]["HOME"])
        assert (runtime_home / ".claude.json").read_text(encoding="utf-8") == (
            '{"hasCompletedOnboarding":true,"auth":"test"}'
        )
        assert (runtime_home / ".claude" / "settings.json").exists()
        assert (runtime_home / ".claude" / "settings.local.json").exists()
        assert not (runtime_home / ".claude" / "history.jsonl").exists()

    async def test_sdk_runtime_env_allows_claude_credentials_only(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
        monkeypatch.setenv("CLAUDE_AUTH_TOKEN", "claude-secret")
        monkeypatch.setenv("SECRET_TOKEN_FULL_VALUE", "must-not-leak")
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        await _collect(adapter, workspace_path=tmp_path)

        assert fake_sdk.last_options is not None
        env = fake_sdk.last_options.kwargs["env"]
        assert env["ANTHROPIC_API_KEY"] == "anthropic-secret"
        assert env["CLAUDE_AUTH_TOKEN"] == "claude-secret"
        assert "SECRET_TOKEN_FULL_VALUE" not in env

    async def test_sdk_copies_shared_claude_auth_into_isolated_home(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        auth_dir = tmp_path / "shared-auth"
        (auth_dir / ".claude").mkdir(parents=True)
        (auth_dir / ".claude.json").write_text('{"source":"shared"}', encoding="utf-8")
        (auth_dir / ".claude" / "session.json").write_text("session", encoding="utf-8")
        monkeypatch.setenv("AGENTHUB_CLAUDE_AUTH_DIR", str(auth_dir))
        fake_sdk = FakeSdk(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        await _collect(adapter, workspace_path=tmp_path)

        assert fake_sdk.last_options is not None
        home = Path(fake_sdk.last_options.kwargs["env"]["HOME"])
        assert (home / ".claude.json").read_text(encoding="utf-8") == '{"source":"shared"}'
        assert (home / ".claude" / "session.json").read_text(encoding="utf-8") == "session"

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

    async def test_sdk_auth_errors_are_normalized(
        self,
        adapter: ClaudeCodeAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake_sdk = FakeSdk(exc=RuntimeError("Claude Code returned an error result: success"))
        monkeypatch.setattr(adapter, "_load_sdk", lambda: fake_sdk)

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "external_runtime_error"
        assert "runtime is not authenticated" in (chunks[1].error or "")
        assert "error result: success" not in (chunks[1].error or "")

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
            env: dict[str, str] | None = None,
        ) -> AsyncIterator[StreamChunk | CliCompleted]:
            _ = command, cwd, budget_config, agent_id, provider, activity_paths, env
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
            env: dict[str, str] | None = None,
        ) -> AsyncIterator[StreamChunk | CliCompleted]:
            _ = cwd, budget_config, agent_id, provider, activity_paths, env
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


def test_claude_code_runtime_status_uses_env_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    claude_code_module._clear_runtime_probe_cache()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("AGENTHUB_CLAUDE_AUTH_DIR", str(tmp_path / "missing-auth"))
    monkeypatch.setattr(
        claude_code_module,
        "_probe_claude_runtime",
        lambda _config=None: ("ready", None),
    )

    status, error = claude_code_module.claude_code_runtime_status()

    assert status == "ready"
    assert error is None


def test_claude_code_runtime_status_uses_shared_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    claude_code_module._clear_runtime_probe_cache()
    auth_dir = tmp_path / "shared-auth"
    auth_dir.mkdir()
    (auth_dir / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("AGENTHUB_CLAUDE_AUTH_DIR", str(auth_dir))
    monkeypatch.setattr(
        claude_code_module,
        "_probe_claude_runtime",
        lambda _config=None: ("ready", None),
    )

    status, error = claude_code_module.claude_code_runtime_status()

    assert status == "ready"
    assert error is None


def test_claude_code_runtime_status_requires_successful_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    claude_code_module._clear_runtime_probe_cache()
    auth_dir = tmp_path / "shared-auth"
    auth_dir.mkdir()
    (auth_dir / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("AGENTHUB_CLAUDE_AUTH_DIR", str(auth_dir))

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        _ = args, kwargs
        return subprocess.CompletedProcess(
            args=["claude"],
            returncode=1,
            stdout="",
            stderr="Not logged in. Please run /login",
        )

    monkeypatch.setattr(claude_code_module.subprocess, "run", fake_run)

    status, error = claude_code_module.claude_code_runtime_status()

    assert status == "unavailable"
    assert error is not None
    assert "runtime is not authenticated" in error


def test_claude_code_runtime_status_unavailable_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    claude_code_module._clear_runtime_probe_cache()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("AGENTHUB_CLAUDE_AUTH_DIR", str(tmp_path / "missing-auth"))

    status, error = claude_code_module.claude_code_runtime_status()

    assert status == "unavailable"
    assert error is not None
    assert "runtime is not authenticated" in error
