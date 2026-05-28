"""Tests for Codex external runtime adapter."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import app.agents.external.codex as codex_module
from app.agents.external.cli_runtime import CliResult
from app.agents.external.codex import CodexAdapter
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
    return [
        chunk
        async for chunk in adapter.stream(
            messages or [ChatMessage(role="user", content="build a page")],
            config=config,
            workspace_path=workspace_path,
        )
    ]


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
        assert "Do not start long-running or background servers" in instructions
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
        assert "Do not start long-running or background servers" in prompt

    async def test_default_runtime_uses_cli_with_danger_sandbox(
        self,
        adapter: CodexAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def fail_load_sdk() -> Any:
            raise AssertionError("SDK should not load for default Codex runtime")

        seen_command: list[str] = []

        async def fake_run_cli_text(
            command: list[str],
            *,
            cwd: Path,
            timeout_seconds: float,
        ) -> CliResult:
            _ = cwd, timeout_seconds
            seen_command.extend(command)
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli default ok\n", encoding="utf-8")
            return CliResult(return_code=0, stdout="ignored", stderr="")

        monkeypatch.setattr(adapter, "_load_sdk", fail_load_sdk)
        monkeypatch.setattr(codex_module, "run_cli_text", fake_run_cli_text)

        chunks = await _collect(adapter, workspace_path=tmp_path)

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "block_end",
            "done",
        ]
        assert chunks[2].text_delta == "codex cli default ok"
        assert seen_command[seen_command.index("--sandbox") + 1] == "danger-full-access"


class TestCodexAdapterErrors:
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

        async def fake_run_cli_text(
            command: list[str],
            *,
            cwd: Path,
            timeout_seconds: float,
        ) -> CliResult:
            _ = cwd, timeout_seconds
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli ok\n", encoding="utf-8")
            return CliResult(return_code=0, stdout="ignored", stderr="")

        monkeypatch.setattr(adapter, "_load_sdk", missing_sdk)
        monkeypatch.setattr(codex_module, "run_cli_text", fake_run_cli_text)

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

        async def fake_run_cli_text(
            command: list[str],
            *,
            cwd: Path,
            timeout_seconds: float,
        ) -> CliResult:
            _ = cwd, timeout_seconds
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli credentials fallback ok\n", encoding="utf-8")
            return CliResult(return_code=0, stdout="ignored", stderr="")

        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))
        monkeypatch.setattr(codex_module, "run_cli_text", fake_run_cli_text)

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

        async def fake_run_cli_text(
            command: list[str],
            *,
            cwd: Path,
            timeout_seconds: float,
        ) -> CliResult:
            _ = cwd, timeout_seconds
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("codex cli stream fallback ok\n", encoding="utf-8")
            return CliResult(return_code=0, stdout="ignored", stderr="")

        monkeypatch.setattr(adapter, "_load_sdk", lambda: FakeSdk(runner))
        monkeypatch.setattr(codex_module, "run_cli_text", fake_run_cli_text)

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
