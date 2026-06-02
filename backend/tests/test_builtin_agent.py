"""Tests for BuiltinAgent MVP."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.agents.builtin.adapter import BuiltinAgentAdapter
from app.agents.builtin.mcp.client import MCPClient, MCPToolCallError
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


class FakeModelGateway:
    def __init__(self, streams: list[list[StreamChunk]]) -> None:
        self.streams = streams
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "config": config,
                "tools": tools,
            }
        )
        chunks = self.streams.pop(0)
        for chunk in chunks:
            yield chunk


class RaisingModelGateway:
    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, tools
        yield StreamChunk(event_type="start", agent_id="fake-model")
        raise RuntimeError("model crashed")


class ToolCallThenRaisingModelGateway:
    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, tools
        yield StreamChunk(
            event_type="tool_call",
            call_id="c-1",
            tool_name="write_file",
            tool_arguments={"path": "a.txt", "content": "x"},
        )
        raise RuntimeError("model crashed after tool_call")


class TimeoutMCPClient(MCPClient):
    async def list_tools(self) -> list[ToolSpec]:
        return [ToolSpec(name="mcp_fs__list_directory", parameters={"type": "object"})]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        _ = tool_name, arguments
        raise MCPToolCallError("MCP tool call timed out")


class HangingProcess:
    def __init__(self) -> None:
        self.killed = False
        self.returncode: int | None = None

    async def communicate(self) -> tuple[bytes, bytes]:
        if not self.killed:
            await asyncio.Event().wait()
        return b"", b""

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


async def _collect(
    adapter: BuiltinAgentAdapter,
    tmp_path: Path,
    *,
    config: dict[str, Any] | None = None,
    tool_specs: list[ToolSpec] | None = None,
) -> list[StreamChunk]:
    return [
        chunk
        async for chunk in adapter.stream(
            [ChatMessage(role="user", content="do it")],
            workspace_path=tmp_path,
            config=config,
            system_prompt="be useful",
            tool_specs=tool_specs,
        )
    ]


def _adapter(
    streams: list[list[StreamChunk]],
    *,
    default_config: dict[str, Any] | None = None,
) -> tuple[BuiltinAgentAdapter, FakeModelGateway]:
    gateway = FakeModelGateway(streams)
    return (
        BuiltinAgentAdapter(
            agent_id="builtin-test",
            default_config=default_config,
            model_gateway=gateway,
        ),
        gateway,
    )


def _text_stream(text: str) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="fake-model"),
        StreamChunk(event_type="block_start", block_index=0, block_type="text"),
        StreamChunk(event_type="delta", block_index=0, text_delta=text),
        StreamChunk(event_type="block_end", block_index=0),
        StreamChunk(event_type="done", agent_id="fake-model", total_blocks=1),
    ]


def _tool_call(name: str, arguments: dict[str, Any], call_id: str = "c-1") -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="fake-model"),
        StreamChunk(
            event_type="tool_call",
            call_id=call_id,
            tool_name=name,
            tool_arguments=arguments,
        ),
        StreamChunk(event_type="done", agent_id="fake-model"),
    ]


def _two_tool_calls() -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="fake-model"),
        StreamChunk(
            event_type="tool_call",
            call_id="c-1",
            tool_name="write_file",
            tool_arguments={"path": "../outside.txt", "content": "bad"},
        ),
        StreamChunk(
            event_type="tool_call",
            call_id="c-2",
            tool_name="write_file",
            tool_arguments={"path": "safe.txt", "content": "safe"},
        ),
        StreamChunk(event_type="done", agent_id="fake-model"),
    ]


async def test_single_turn_text_response_done(tmp_path: Path) -> None:
    adapter, _gateway = _adapter([_text_stream("hello")])

    chunks = await _collect(adapter, tmp_path)

    assert [chunk.event_type for chunk in chunks] == [
        "start",
        "block_start",
        "delta",
        "block_end",
        "done",
    ]
    assert chunks[2].text_delta == "hello"


async def test_configured_empty_allowed_tools_exposes_no_tools(tmp_path: Path) -> None:
    adapter, gateway = _adapter(
        [_text_stream("hello")],
        default_config={"allowed_tools": []},
    )

    await _collect(adapter, tmp_path)

    assert gateway.calls[0]["tools"] == []


async def test_configured_allowed_tools_filters_native_tools(tmp_path: Path) -> None:
    adapter, gateway = _adapter(
        [_text_stream("hello")],
        default_config={"allowed_tools": ["read_file"]},
    )

    await _collect(adapter, tmp_path)

    assert [tool.name for tool in gateway.calls[0]["tools"]] == ["read_file"]


async def test_tool_specs_cannot_expand_configured_allowed_tools(tmp_path: Path) -> None:
    adapter, gateway = _adapter(
        [_text_stream("hello")],
        default_config={"allowed_tools": ["read_file", "write_file"]},
    )

    await _collect(
        adapter,
        tmp_path,
        tool_specs=[
            ToolSpec(name="write_file", parameters={"type": "object"}),
            ToolSpec(name="bash", parameters={"type": "object"}),
        ],
    )

    assert [tool.name for tool in gateway.calls[0]["tools"]] == ["write_file"]


async def test_write_file_success_and_call_id_pairing(tmp_path: Path) -> None:
    adapter, gateway = _adapter(
        [
            _tool_call("write_file", {"path": "src/App.tsx", "content": "export default 1"}),
            _text_stream("written"),
        ]
    )

    chunks = await _collect(adapter, tmp_path)

    assert (tmp_path / "src" / "App.tsx").read_text(encoding="utf-8") == "export default 1"
    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert tool_call.call_id == "c-1"
    assert tool_result.call_id == "c-1"
    assert tool_result.tool_status == "ok"
    assert len(gateway.calls) == 2
    assert "Tool write_file (c-1) ok" in gateway.calls[1]["messages"][-1].content
    assert [tool.name for tool in gateway.calls[0]["tools"]] == [
        "read_file",
        "write_file",
        "bash",
    ]


async def test_write_file_accepts_file_path_alias(tmp_path: Path) -> None:
    adapter, _gateway = _adapter(
        [
            _tool_call("write_file", {"file_path": "snake.html", "content": "ok"}),
            _text_stream("written"),
        ]
    )

    chunks = await _collect(adapter, tmp_path)

    assert (tmp_path / "snake.html").read_text(encoding="utf-8") == "ok"
    result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert result.tool_status == "ok"
    assert result.tool_output == "wrote snake.html (2 bytes)"


async def test_read_file_success_uses_model_gateway_fake_path(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello file", encoding="utf-8")
    adapter, gateway = _adapter(
        [
            _tool_call("read_file", {"path": "notes.txt"}),
            _text_stream("read"),
        ]
    )

    chunks = await _collect(adapter, tmp_path)

    result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert result.tool_status == "ok"
    assert result.tool_output == "hello file"
    assert gateway.calls[0]["system_prompt"] == "be useful"


@pytest.mark.parametrize("tool_name", ["read_file", "write_file"])
async def test_workspace_tools_reject_path_escape(tmp_path: Path, tool_name: str) -> None:
    arguments = {"path": "../outside.txt"}
    if tool_name == "write_file":
        arguments["content"] = "bad"
    adapter, _gateway = _adapter([_tool_call(tool_name, arguments)])

    chunks = await _collect(adapter, tmp_path)

    tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")

    assert tool_result.call_id == "c-1"
    assert tool_result.tool_status == "error"
    assert tool_result.metadata == {"error_code": "workspace_violation"}
    assert chunks[-1].event_type == "error"
    assert chunks[-1].error_code == "workspace_violation"


async def test_bash_whitelist_rejects_curl(tmp_path: Path) -> None:
    adapter, _gateway = _adapter(
        [
            _tool_call("bash", {"command": "curl http://example.com"}),
            _text_stream("retry without curl"),
        ]
    )

    chunks = await _collect(adapter, tmp_path)

    result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert result.tool_status == "error"
    assert result.metadata == {"error_code": "tool_call_failed"}
    assert "not allowed" in (result.tool_output or "")
    assert chunks[-1].event_type == "done"


async def test_bash_rejects_python_execution(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    script = f"open('../{outside.name}', 'w', encoding='utf-8').write('escaped')"
    adapter, _gateway = _adapter([_tool_call("bash", {"command": f"python -c \"{script}\""})])

    chunks = await _collect(adapter, tmp_path)

    result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert result.tool_status == "error"
    assert result.metadata == {"error_code": "tool_call_failed"}
    assert outside.exists() is False


async def test_bash_rejects_path_escape(tmp_path: Path) -> None:
    adapter, _gateway = _adapter([_tool_call("bash", {"command": "cat ../outside.txt"})])

    chunks = await _collect(adapter, tmp_path)

    result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert result.tool_status == "error"
    assert result.metadata == {"error_code": "workspace_violation"}
    assert chunks[-1].event_type == "error"
    assert chunks[-1].error_code == "workspace_violation"


async def test_bash_timeout_maps_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = HangingProcess()

    async def fake_create_subprocess_exec(*_argv: str, **_kwargs: Any) -> HangingProcess:
        return process

    monkeypatch.setattr(
        "app.agents.builtin.tools.bash.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    adapter, _gateway = _adapter(
        [
            _tool_call("bash", {"command": "cat slow.txt"}),
            _text_stream("timed out"),
        ]
    )

    chunks = await _collect(adapter, tmp_path, config={"bash_timeout_seconds": 0.01})

    result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert process.killed is True
    assert result.tool_status == "error"
    assert result.metadata == {"error_code": "timeout"}


async def test_workspace_violation_still_pairs_later_tool_calls(tmp_path: Path) -> None:
    adapter, _gateway = _adapter([_two_tool_calls()])

    chunks = await _collect(adapter, tmp_path)

    call_ids = [chunk.call_id for chunk in chunks if chunk.event_type == "tool_call"]
    result_ids = [chunk.call_id for chunk in chunks if chunk.event_type == "tool_result"]
    assert call_ids == ["c-1", "c-2"]
    assert result_ids == ["c-1", "c-2"]
    assert chunks[-1].event_type == "error"
    assert chunks[-1].error_code == "workspace_violation"


async def test_model_stream_exception_maps_upstream_error(tmp_path: Path) -> None:
    adapter = BuiltinAgentAdapter(
        agent_id="builtin-test",
        model_gateway=RaisingModelGateway(),
    )

    chunks = await _collect(adapter, tmp_path)

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[-1].error_code == "upstream_error"


async def test_model_stream_exception_after_tool_call_pairs_result(tmp_path: Path) -> None:
    adapter = BuiltinAgentAdapter(
        agent_id="builtin-test",
        model_gateway=ToolCallThenRaisingModelGateway(),
    )

    chunks = await _collect(adapter, tmp_path)

    assert [chunk.event_type for chunk in chunks] == [
        "start",
        "tool_call",
        "tool_result",
        "error",
    ]
    assert chunks[1].call_id == "c-1"
    assert chunks[2].call_id == "c-1"
    assert chunks[-1].error_code == "upstream_error"


async def test_mcp_tool_timeout_maps_tool_call_failed(tmp_path: Path) -> None:
    adapter = BuiltinAgentAdapter(
        agent_id="builtin-test",
        model_gateway=FakeModelGateway(
            [
                _tool_call("mcp_fs__list_directory", {"path": "."}),
                _text_stream("handled"),
            ]
        ),
        mcp_client=TimeoutMCPClient(),
    )

    chunks = await _collect(adapter, tmp_path)

    result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert result.tool_status == "error"
    assert result.metadata == {"error_code": "tool_call_failed"}
    assert chunks[-1].event_type == "done"


async def test_loop_max_iterations(tmp_path: Path) -> None:
    adapter, _gateway = _adapter(
        [_tool_call("write_file", {"path": "a.txt", "content": "x"})]
    )

    chunks = await _collect(adapter, tmp_path, config={"max_iterations": 1})

    assert chunks[-1].event_type == "error"
    assert chunks[-1].error_code == "loop_max_iterations"


async def test_mcp_server_down_maps_error(tmp_path: Path) -> None:
    adapter = BuiltinAgentAdapter(
        agent_id="builtin-test",
        default_config={
            "mcp_servers": [
                {"name": "fs", "command": "agenthub-missing-mcp-server", "args": []}
            ]
        },
        model_gateway=FakeModelGateway([_text_stream("unused")]),
    )

    chunks = await _collect(adapter, tmp_path)

    assert [chunk.event_type for chunk in chunks] == ["error"]
    assert chunks[0].error_code == "mcp_server_down"


async def test_missing_workspace_maps_workspace_violation() -> None:
    adapter, _gateway = _adapter([_text_stream("unused")])

    chunks = [
        chunk
        async for chunk in adapter.stream([ChatMessage(role="user", content="do it")])
    ]

    assert [chunk.event_type for chunk in chunks] == ["error"]
    assert chunks[0].error_code == "workspace_violation"
