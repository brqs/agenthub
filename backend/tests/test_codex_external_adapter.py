"""Tests for Codex external runtime adapter."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import app.agents.external.codex as codex_module
from app.agents.external.cli_runtime import CliCompleted, CliResult
from app.agents.external.codex import CodexAdapter
from app.agents.external.direct_chat import DirectChatDecision
from app.agents.external.runtime_budget import RuntimeTimeoutError
from app.agents.types import ChatMessage, StreamChunk


class FakeManifest:
    def __init__(self, *, root: str) -> None:
        self.root = root


class FakeUnixLocalSandboxClient:
    pass


class FakeUnixLocalSandboxClientOptions:
    def __init__(self, *, exposed_ports: tuple[int, ...] = ()) -> None:
        self.exposed_ports = exposed_ports


class FakeSandboxRunConfig:
    def __init__(
        self,
        *,
        client: FakeUnixLocalSandboxClient,
        options: FakeUnixLocalSandboxClientOptions,
        manifest: FakeManifest,
    ) -> None:
        self.client = client
        self.options = options
        self.manifest = manifest


class FakeRunConfig:
    def __init__(
        self,
        *,
        model: str,
        sandbox: FakeSandboxRunConfig,
        workflow_name: str,
    ) -> None:
        self.model = model
        self.sandbox = sandbox
        self.workflow_name = workflow_name


class FakeSandboxAgent:
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


class FakeRunResult:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def stream_events(self) -> FakeEventStream:
        return FakeEventStream(self.events)


class FakeRunner:
    def __init__(
        self,
        events: list[Any] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.events = events or []
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    def run_streamed(
        self,
        starting_agent: FakeSandboxAgent,
        input: str,
        *,
        run_config: FakeRunConfig,
    ) -> FakeRunResult:
        self.calls.append(
            {
                "agent": starting_agent,
                "input": input,
                "run_config": run_config,
            }
        )
        if self.exc:
            raise self.exc
        return FakeRunResult(self.events)


class FakeSdk:
    Manifest = FakeManifest
    RunConfig = FakeRunConfig
    SandboxAgent = FakeSandboxAgent
    SandboxRunConfig = FakeSandboxRunConfig
    UnixLocalSandboxClient = FakeUnixLocalSandboxClient
    UnixLocalSandboxClientOptions = FakeUnixLocalSandboxClientOptions

    def __init__(self, runner: FakeRunner) -> None:
        self.Runner = runner


class FakeAuthenticationError(Exception):
    """SDK auth error used by fake OpenAI Agents SDK."""


def _raw_text_event(delta: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="raw_response_event",
        data=SimpleNamespace(type="response.output_text.delta", delta=delta),
    )


def _tool_call_event() -> SimpleNamespace:
    return SimpleNamespace(
        type="run_item_stream_event",
        item=SimpleNamespace(
            type="tool_call_item",
            raw_item=SimpleNamespace(
                call_id="call-1",
                name="write_file",
                arguments='{"path": "App.tsx"}',
            ),
        ),
    )


def _tool_output_event() -> SimpleNamespace:
    return SimpleNamespace(
        type="run_item_stream_event",
        item=SimpleNamespace(
            type="tool_call_output_item",
            raw_item=SimpleNamespace(call_id="call-1"),
            output="updated App.tsx",
        ),
    )


async def _collect(
    adapter: CodexAdapter,
    *,
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


def _fake_stream_cli_text(
    result: CliResult,
    *,
    on_command: Any | None = None,
) -> Any:
    async def fake(
        command: list[str],
        *,
        cwd: Path,
        budget_config: Any,
        agent_id: str,
        provider: str,
        activity_paths: list[Path] | None = None,
    ) -> AsyncIterator[StreamChunk | CliCompleted]:
        _ = cwd, budget_config, agent_id, provider, activity_paths
        if on_command is not None:
            on_command(command)
        yield CliCompleted(result)

    return fake


class TestCodexDirectChat:
    async def test_direct_chat_does_not_start_cli(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fake_direct_chat(**_kwargs: Any) -> DirectChatDecision:
            async def stream() -> AsyncIterator[StreamChunk]:
                yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
                yield StreamChunk(event_type="delta", block_index=0, text_delta="direct")
                yield StreamChunk(event_type="block_end", block_index=0)
                yield StreamChunk(event_type="done", agent_id="codex-test", total_blocks=1)

            return DirectChatDecision(route="direct_chat", stream=stream())

        async def fail_stream_cli_text(*_args: Any, **_kwargs: Any) -> AsyncIterator[Any]:
            pytest.fail("Codex CLI should not start for direct chat")
            yield  # pragma: no cover

        monkeypatch.setattr(codex_module, "maybe_stream_direct_chat", fake_direct_chat)
        monkeypatch.setattr(codex_module, "stream_cli_text", fail_stream_cli_text)

        chunks = await _collect(
            CodexAdapter(agent_id="codex-test"),
            workspace_path=tmp_path,
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

    async def test_simple_greeting_returns_direct_text_without_cli_or_classifier(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fail_direct_chat(**_kwargs: Any) -> DirectChatDecision:
            pytest.fail("simple greetings should not start the direct-chat classifier")

        async def fail_stream_cli_text(*_args: Any, **_kwargs: Any) -> AsyncIterator[Any]:
            pytest.fail("Codex CLI should not start for simple greetings")
            yield  # pragma: no cover

        monkeypatch.setattr(codex_module, "maybe_stream_direct_chat", fail_direct_chat)
        monkeypatch.setattr(codex_module, "stream_cli_text", fail_stream_cli_text)

        chunks = await _collect(
            CodexAdapter(agent_id="codex-test"),
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
        assert "Codex Helper" in (chunks[2].text_delta or "")


def _fake_stream_cli_timeout(
    *,
    on_command: Any | None = None,
    error_code: str = "runtime_hard_timeout",
    stdout: str = "",
    stderr: str = "",
) -> Any:
    async def fake(
        command: list[str],
        *,
        cwd: Path,
        budget_config: Any,
        agent_id: str,
        provider: str,
        activity_paths: list[Path] | None = None,
    ) -> AsyncIterator[StreamChunk | CliCompleted]:
        _ = cwd, budget_config, agent_id, provider, activity_paths
        if on_command is not None:
            on_command(command)
        raise RuntimeTimeoutError(error_code, "runtime timed out", stdout=stdout, stderr=stderr)
        yield  # pragma: no cover

    return fake


@pytest.fixture
def adapter() -> CodexAdapter:
    return CodexAdapter(agent_id="agent-codex")


class TestCodexAdapterStream:
    async def test_text_stream_maps_to_text_block(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(
            events=[
                _raw_text_event("Hello"),
                _raw_text_event(" world"),
            ]
        )
        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[0].agent_id == "agent-codex"
        assert chunks[1].block_type == "text"
        assert chunks[2].text_delta == "Hello"
        assert chunks[3].text_delta == " world"
        assert chunks[-1].total_blocks == 1

    async def test_text_stream_removes_preview_server_commands(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(
            events=[
                _raw_text_event("Created snake.html.\nUse `next "),
                _raw_text_event("dev --hostname 0.0.0.0`."),
            ]
        )
        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})
        text = "".join(chunk.text_delta or "" for chunk in chunks)

        assert "Created snake.html" in text
        assert "next dev" not in text
        assert "Preview/deploy server commands are handled by AgentHub" in text

    async def test_tool_call_and_result_preserve_call_id(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(
            events=[
                _tool_call_event(),
                _tool_output_event(),
            ]
        )
        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})

        tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
        tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")

        assert tool_call.call_id == "call-1"
        assert tool_call.tool_name == "write_file"
        assert tool_call.tool_arguments == {"path": "App.tsx"}
        assert tool_result.call_id == "call-1"
        assert tool_result.tool_status == "ok"
        assert tool_result.tool_output == "updated App.tsx"
        assert chunks[-1].total_blocks == 0

    async def test_workspace_path_is_used_as_sandbox_root(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(events=[])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))

        await _collect(
            adapter,
            workspace_path=tmp_path,
            config={
                "runtime": "sdk",
                "runtime_options": {"approval_policy": "never", "exposed_ports": [3000]},
            },
        )

        call = runner.calls[0]
        instructions = call["agent"].kwargs["instructions"]
        run_config = call["run_config"]
        assert str(tmp_path) in instructions
        assert "Workspace root:" in instructions
        assert "Never write to /home/user" in instructions
        assert "Do not run, suggest, or print shell commands" in instructions
        assert "Do not provide terminal commands for port previews" in instructions
        assert "do not create a Node/Express" in instructions
        assert "server.js" in instructions
        assert "Treat the latest user message as the only active request" in instructions
        assert "python3 -m http.server 8082" not in instructions
        assert isinstance(run_config.sandbox.client, FakeUnixLocalSandboxClient)
        assert run_config.sandbox.manifest.root == str(tmp_path)
        assert run_config.sandbox.options.exposed_ports == (3000,)
        assert not hasattr(run_config.sandbox.options, "approval_policy")

    def test_cli_prompt_includes_workspace_rules(
        self,
        adapter: CodexAdapter,
        tmp_path: Path,
    ) -> None:
        prompt = adapter._format_cli_prompt(
            [ChatMessage(role="user", content="build a page")],
            None,
            tmp_path,
        )

        assert str(tmp_path) in prompt
        assert "Workspace root:" in prompt
        assert "Never write to /home/user" in prompt
        assert "Do not run, suggest, or print shell commands" in prompt
        assert "Do not provide terminal commands for port previews" in prompt
        assert "do not create a Node/Express" in prompt
        assert "server.js" in prompt
        assert "Treat the latest user message as the only active request" in prompt
        assert "python3 -m http.server 8082" not in prompt

    def test_cli_prompt_marks_latest_user_request(
        self,
        adapter: CodexAdapter,
        tmp_path: Path,
    ) -> None:
        prompt = adapter._format_cli_prompt(
            [
                ChatMessage(role="user", content="create a snake game"),
                ChatMessage(role="assistant", content="I created snake-game/index.html"),
                ChatMessage(role="user", content="你是什么模型"),
            ],
            None,
            tmp_path,
        )

        assert "Previous conversation context (not the active task):" in prompt
        assert "Current user request (answer this now):\n你是什么模型" in prompt
        assert prompt.index("create a snake game") < prompt.index("Current user request")

    async def test_identity_question_returns_direct_text_without_runtime(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        async def fail_stream_cli_text(
            command: list[str],
            *,
            cwd: Path,
            budget_config: Any,
            agent_id: str,
            provider: str,
            activity_paths: list[Path] | None = None,
        ) -> AsyncIterator[StreamChunk | CliCompleted]:
            _ = command, cwd, budget_config, agent_id, provider, activity_paths
            raise AssertionError("identity questions must not start Codex CLI")
            yield  # pragma: no cover

        monkeypatch.setattr(codex_module, "stream_cli_text", fail_stream_cli_text)

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
        assert "我是 Codex Helper" in (chunks[2].text_delta or "")
        assert chunks[-1].total_blocks == 1

    async def test_default_runtime_uses_cli_with_danger_sandbox(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def fail_load_sdk() -> Any:
            raise AssertionError("SDK should not load for default Codex runtime")

        seen_command: list[str] = []

        def write_output(command: list[str]) -> None:
            seen_command.extend(command)
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli default ok\n", encoding="utf-8")

        monkeypatch.setattr(adapter, "_load_sdk", fail_load_sdk)
        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(return_code=0, stdout="ignored", stderr=""),
                on_command=write_output,
            ),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "codex cli default ok"
        assert seen_command[0].endswith("codex")
        assert seen_command[seen_command.index("--sandbox") + 1] == "danger-full-access"

    async def test_cli_runtime_uses_configured_command(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        seen_command: list[str] = []

        def write_output(command: list[str]) -> None:
            seen_command.extend(command)
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("custom codex command ok\n", encoding="utf-8")

        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(return_code=0, stdout="ignored", stderr=""),
                on_command=write_output,
            ),
        )

        chunks = await _collect(
            adapter,
            config={"command": "/tmp/custom-codex-cli"},  # noqa: S108
            workspace_path=tmp_path,
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "custom codex command ok"
        assert seen_command[0] == "/tmp/custom-codex-cli"

    async def test_cli_output_removes_preview_server_commands(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def write_output(command: list[str]) -> None:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                "Created snake.html.\nRun `pnpm dev --host 0.0.0.0`.\n",
                encoding="utf-8",
            )

        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(return_code=0, stdout="ignored", stderr=""),
                on_command=write_output,
            ),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path)
        text = "".join(chunk.text_delta or "" for chunk in chunks)

        assert "Created snake.html" in text
        assert "pnpm dev" not in text
        assert "Preview/deploy server commands are handled by AgentHub" in text

    async def test_cli_timeout_with_output_file_completes(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def write_output(command: list[str]) -> None:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex finished before timeout\n", encoding="utf-8")

        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_timeout(on_command=write_output),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "codex finished before timeout"
        assert chunks[-1].total_blocks == 1
        assert list(tmp_path.glob(".agenthub_codex_*.txt")) == []

    async def test_cli_timeout_without_output_file_remains_timeout(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(codex_module, "stream_cli_text", _fake_stream_cli_timeout())

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "runtime_hard_timeout"
        assert "Codex CLI timed out" in (chunks[1].error or "")
        assert list(tmp_path.glob(".agenthub_codex_*.txt")) == []


class TestCodexAdapterErrors:
    async def test_cli_nonzero_logs_full_redacted_stdout_stderr(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level("ERROR", logger=codex_module.__name__)
        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(
                    return_code=1,
                    stdout=(
                        "stdout-start "
                        + ("a" * 650)
                        + " stdout-tail OPENAI_API_KEY=sk-testsecret123456"
                    ),
                    stderr=(
                        "stderr-start "
                        + ("b" * 650)
                        + " stderr-tail Authorization: Bearer secret-token-123456"
                    ),
                )
            ),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "external_runtime_error"
        assert "stdout-tail" in caplog.text
        assert "stderr-tail" in caplog.text
        assert "sk-testsecret123456" not in caplog.text
        assert "secret-token-123456" not in caplog.text

    async def test_cli_nonzero_error_includes_redacted_stdout_stderr_and_output_file(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def write_output(command: list[str]) -> None:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("partial output sk-abcdef123456", encoding="utf-8")

        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(
                    return_code=1,
                    stdout="stdout detail",
                    stderr="stderr detail Bearer secret-token-123456",
                ),
                on_command=write_output,
            ),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "external_runtime_error"
        assert "stderr:\nstderr detail Bearer [redacted]" in (chunks[1].error or "")
        assert "stdout:\nstdout detail" in (chunks[1].error or "")
        assert "output_file:\npartial output [redacted]" in (chunks[1].error or "")

    async def test_sdk_authentication_error_maps_missing_api_key(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(exc=FakeAuthenticationError("No API key provided"))
        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "missing_api_key"

    async def test_sdk_stream_exception_maps_external_runtime_error(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(events=[RuntimeError("runtime crashed")])
        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "external_runtime_error"
        assert "runtime crashed" in (chunks[1].error or "")

    async def test_missing_sdk_falls_back_to_logged_in_cli(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def missing_sdk() -> Any:
            raise ModuleNotFoundError("No module named 'agents'", name="agents")

        def write_output(command: list[str]) -> None:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli ok\n", encoding="utf-8")

        monkeypatch.setattr(adapter, "_load_sdk", missing_sdk)
        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(return_code=0, stdout="ignored", stderr=""),
                on_command=write_output,
            ),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "codex cli ok"

    async def test_sdk_missing_credentials_falls_back_to_logged_in_cli(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(
            exc=RuntimeError(
                "Missing credentials. Please set the OPENAI_API_KEY environment variable."
            )
        )

        def write_output(command: list[str]) -> None:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli credentials fallback ok\n", encoding="utf-8")

        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))
        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(return_code=0, stdout="ignored", stderr=""),
                on_command=write_output,
            ),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "codex cli credentials fallback ok"

    async def test_sdk_stream_missing_credentials_falls_back_to_logged_in_cli(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        runner = FakeRunner(
            events=[
                RuntimeError(
                    "Missing credentials. Please set the OPENAI_API_KEY environment variable."
                )
            ]
        )

        def write_output(command: list[str]) -> None:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli stream fallback ok\n", encoding="utf-8")

        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))
        monkeypatch.setattr(
            codex_module,
            "stream_cli_text",
            _fake_stream_cli_text(
                CliResult(return_code=0, stdout="ignored", stderr=""),
                on_command=write_output,
            ),
        )

        chunks = await _collect(adapter, workspace_path=tmp_path, config={"runtime": "sdk"})

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "codex cli stream fallback ok"

    async def test_missing_workspace_path_does_not_load_sdk(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fail_load_sdk() -> Any:
            raise AssertionError("SDK should not load without workspace_path")

        monkeypatch.setattr(adapter, "_load_sdk", fail_load_sdk)

        chunks = await _collect(adapter, workspace_path=None)

        assert [chunk.event_type for chunk in chunks] == ["start", "error"]
        assert chunks[1].error_code == "workspace_violation"


def test_codex_adapter_does_not_import_raw_openai_adapter() -> None:
    source = inspect.getsource(codex_module)

    assert "app.agents.adapters.openai" not in source
    assert "app.agents.model_gateway.openai" not in source
