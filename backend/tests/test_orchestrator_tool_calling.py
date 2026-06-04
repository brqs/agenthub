"""Tests for Orchestrator native tool calling."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.orchestrator.tools import OrchestratorToolResult
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


class FakeGateway:
    def __init__(self, chunk_sequences: list[list[StreamChunk]]) -> None:
        self._chunk_sequences = chunk_sequences
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
                "messages": list(messages),
                "system_prompt": system_prompt,
                "config": config,
                "tools": tools,
            }
        )
        index = len(self.calls) - 1
        chunks = self._chunk_sequences[index] if index < len(self._chunk_sequences) else []
        for chunk in chunks:
            yield chunk


class FakeWriterAdapter(BaseAgentAdapter):
    provider = "fake"

    def __init__(self, agent_id: str, path: str, content: str) -> None:
        super().__init__(agent_id=agent_id)
        self.path = path
        self.content = content
        self.received_messages: list[ChatMessage] = []

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = system_prompt, config, tool_specs
        self.received_messages = messages
        if workspace_path is not None:
            (workspace_path / self.path).write_text(self.content, encoding="utf-8")
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(
            event_type="tool_call",
            call_id="write-1",
            tool_name="write_file",
            tool_arguments={"path": self.path},
        )
        yield StreamChunk(
            event_type="tool_result",
            call_id="write-1",
            tool_status="ok",
            tool_output=f"wrote {self.path}",
        )
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta=f"Created {self.path}",
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)


class FakeMemoryWriter:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.started: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.started_tasks: list[dict[str, Any]] = []
        self.task_results: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []

    async def start_run(
        self,
        *,
        user_request: str,
        plan_source: str,
        tasks: list[Any],
    ) -> Any:
        self.started.append(
            {
                "user_request": user_request,
                "plan_source": plan_source,
                "tasks": tasks,
            }
        )
        return self.run_id

    async def record_task_started(
        self,
        *,
        run_id: Any,
        task: Any,
        agent_id: str,
        attempt_index: int,
    ) -> None:
        self.started_tasks.append(
            {
                "run_id": run_id,
                "task_id": task.task_id,
                "agent_id": agent_id,
                "attempt_index": attempt_index,
            }
        )

    async def record_task_result(self, *, run_id: Any, task: Any, result: Any) -> None:
        self.task_results.append(
            {
                "run_id": run_id,
                "task_id": task.task_id,
                "state": result.final_state.value,
            }
        )

    async def record_event(
        self,
        *,
        run_id: Any,
        event_type: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "run_id": run_id,
                "event_type": event_type,
                "task_id": task_id,
                "agent_id": agent_id,
                "payload": payload,
            }
        )

    async def finish_run(
        self,
        *,
        run_id: Any,
        status: str,
        final_summary: str,
    ) -> None:
        self.finished.append(
            {
                "run_id": run_id,
                "status": status,
                "final_summary": final_summary,
            }
        )


class FakePlatformExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> OrchestratorToolResult:
        self.calls.append((tool_name, arguments))
        return OrchestratorToolResult(
            status="ok",
            output=(
                '{"status":"ok","agent":{"id":"custom-1","name":"LiveCopywriter",'
                '"provider":"builtin","capabilities":["copywriting","review"],'
                '"allowed_tools":[],"is_builtin":false},"added_to_conversation":true}'
            ),
        )


async def _collect(
    adapter: OrchestratorAdapter,
    *,
    messages: list[ChatMessage] | None = None,
    config: dict[str, Any],
    workspace_path: Path | None = None,
) -> list[StreamChunk]:
    return [
        chunk
        async for chunk in adapter.stream(
            messages=messages or [ChatMessage(role="user", content="Create a smoke file")],
            config=config,
            workspace_path=workspace_path,
        )
    ]


async def test_conversational_custom_agent_uses_platform_tool_without_tool_loop() -> None:
    executor = FakePlatformExecutor()
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 请创建一个新的自建 Agent，名字为 LiveCopywriter，"
                    "provider 使用 builtin，system_prompt 为“你是中文文案 Agent”，"
                    "capabilities 设置为 copywriting、review，并把它加入当前群聊。"
                ),
            )
        ],
        config={
            "orchestrator_platform_tool_executor": executor,
            "orchestrator_tool_calling_enabled": False,
        },
    )

    assert executor.calls == [
        (
            "create_custom_agent",
            {
                "name": "LiveCopywriter",
                "provider": "builtin",
                "system_prompt": "你是中文文案 Agent",
                "capabilities": ["copywriting", "review"],
                "config": {},
                "add_to_conversation": True,
            },
        )
    ]
    assert [chunk.tool_name for chunk in chunks if chunk.event_type == "tool_call"] == [
        "create_custom_agent"
    ]
    assert [chunk.tool_status for chunk in chunks if chunk.event_type == "tool_result"] == [
        "ok"
    ]
    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert "custom-1" in text
    assert chunks[-1].event_type == "done"


async def test_conversational_custom_agent_forwards_allowed_tools() -> None:
    executor = FakePlatformExecutor()
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 请创建一个新的自建 Agent，名字为 ReaderAgent，"
                    "provider 使用 builtin，system_prompt 为“你是阅读 Agent”，"
                    "工具白名单设置为 read_file、write_file，并把它加入当前群聊。"
                ),
            )
        ],
        config={
            "orchestrator_platform_tool_executor": executor,
            "orchestrator_tool_calling_enabled": False,
        },
    )

    assert executor.calls[0][1]["allowed_tools"] == ["read_file", "write_file"]


def _tool_call(
    name: str,
    arguments: dict[str, Any],
    *,
    call_id: str = "raw-call",
) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="tool-loop"),
        StreamChunk(
            event_type="tool_call",
            call_id=call_id,
            tool_name=name,
            tool_arguments=arguments,
        ),
        StreamChunk(event_type="done", agent_id="tool-loop"),
    ]


def _text_response(text: str) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="tool-loop"),
        StreamChunk(event_type="block_start", block_index=0, block_type="text"),
        StreamChunk(event_type="delta", block_index=0, text_delta=text),
        StreamChunk(event_type="block_end", block_index=0),
        StreamChunk(event_type="done", agent_id="tool-loop", total_blocks=1),
    ]


async def test_tool_calling_dispatches_agent_validates_html_and_finishes(
    tmp_path: Path,
) -> None:
    html_path = "tool-loop-smoke.html"
    html = """<!doctype html>
<html>
<head><title>Tool Loop Smoke</title></head>
<body><input id="name"><button>Show</button><script>console.log("ok")</script></body>
</html>
"""
    gateway = FakeGateway(
        [
            _tool_call(
                "dispatch_agent",
                {
                    "task_id": "create-html",
                    "agent_id": "codex-helper",
                    "title": "Create HTML",
                    "instruction": f"Create {html_path}.",
                    "expected_output": html_path,
                },
            ),
            _tool_call(
                "validate_html",
                {
                    "path": html_path,
                    "required_title": "Tool Loop Smoke",
                    "require_input": True,
                    "require_button": True,
                    "require_script": True,
                },
            ),
            _text_response("完成：文件已生成并通过静态 HTML 校验。"),
        ]
    )
    writer = FakeWriterAdapter("codex-helper", html_path, html)
    memory = FakeMemoryWriter()
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "orchestrator_tool_calling_enabled": True,
            "orchestrator_tool_gateway": gateway,
            "orchestrator_memory_writer": memory,
            "managed_agent_ids": ["codex-helper"],
            "sub_adapters": {"codex-helper": writer},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[0].event_type == "start"
    assert chunks[-1].event_type == "done"
    assert (tmp_path / html_path).exists()
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "codex-helper"
    ]
    assert [chunk.call_id for chunk in chunks if chunk.event_type == "tool_call"] == [
        "orch.1.1",
        "orch.1.1.child.write-1",
        "orch.2.1",
    ]
    assert "完成" in text
    assert len(gateway.calls) == 3
    assert {tool.name for tool in gateway.calls[0]["tools"]} == {
        "dispatch_agent",
        "inspect_workspace",
        "read_artifact",
        "validate_html",
        "start_workspace_preview",
        "verify_web_preview",
        "create_custom_agent",
        "create_deployment",
        "get_deployment_status",
        "stop_deployment",
        "package_workspace_source",
        "ask_user",
    }
    assert "Tool dispatch_agent (orch.1.1) ok" in gateway.calls[1]["messages"][-1].content
    assert "Tool validate_html (orch.2.1) ok" in gateway.calls[2]["messages"][-1].content
    assert memory.started[0]["plan_source"] == "tool_calling"
    assert memory.started_tasks[0]["task_id"] == "create-html"
    assert memory.task_results[0]["state"] == "succeeded"
    assert [
        event["payload"]["tool_name"]
        for event in memory.events
        if event["event_type"] == "tool_call"
    ] == [
        "dispatch_agent",
        "validate_html",
    ]
    assert memory.finished[-1]["status"] == "done"


async def test_tool_calling_rejects_group_external_agent() -> None:
    gateway = FakeGateway(
        [
            _tool_call(
                "dispatch_agent",
                {
                    "agent_id": "web-designer",
                    "title": "Out of group",
                    "instruction": "Do work.",
                },
            ),
            _text_response("没有调用群聊外 agent。"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "orchestrator_tool_calling_enabled": True,
            "orchestrator_tool_gateway": gateway,
            "managed_agent_ids": ["codex-helper"],
            "sub_adapters": {},
        },
    )

    tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert chunks[-1].event_type == "done"
    assert tool_result.tool_status == "error"
    assert tool_result.metadata == {"error_code": "agent_not_allowed"}
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert "agent is not available" in gateway.calls[1]["messages"][-1].content


async def test_tool_calling_hides_orchestrator_tool_trace_but_keeps_child_output(
    tmp_path: Path,
) -> None:
    html_path = "hidden-trace.html"
    gateway = FakeGateway(
        [
            _tool_call(
                "dispatch_agent",
                {
                    "agent_id": "codex-helper",
                    "title": "Create HTML",
                    "instruction": f"Create {html_path}.",
                },
            ),
            _text_response("已完成。"),
        ]
    )
    writer = FakeWriterAdapter("codex-helper", html_path, "<html></html>")
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "orchestrator_tool_calling_enabled": True,
            "orchestrator_tool_trace_visible": False,
            "orchestrator_subagent_text_visible": True,
            "orchestrator_tool_gateway": gateway,
            "managed_agent_ids": ["codex-helper"],
            "sub_adapters": {"codex-helper": writer},
        },
    )

    tool_calls = [chunk for chunk in chunks if chunk.event_type == "tool_call"]
    tool_results = [chunk for chunk in chunks if chunk.event_type == "tool_result"]
    assert [chunk.call_id for chunk in tool_calls] == ["orch.1.1.child.write-1"]
    assert [chunk.call_id for chunk in tool_results] == ["orch.1.1.child.write-1"]
    assert any("Created hidden-trace.html" in (chunk.text_delta or "") for chunk in chunks)
    assert chunks[-1].event_type == "done"


async def test_tool_calling_read_artifact_rejects_workspace_escape(
    tmp_path: Path,
) -> None:
    gateway = FakeGateway(
        [
            _tool_call("read_artifact", {"path": "../secret.txt"}),
            _text_response("无法读取 workspace 外路径。"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "orchestrator_tool_calling_enabled": True,
            "orchestrator_tool_gateway": gateway,
            "managed_agent_ids": ["codex-helper"],
            "sub_adapters": {},
        },
    )

    tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert chunks[-1].event_type == "done"
    assert tool_result.tool_status == "error"
    assert tool_result.metadata == {"error_code": "workspace_violation"}
    assert "parent path traversal" in (tool_result.tool_output or "")


async def test_tool_calling_max_iterations_returns_error() -> None:
    gateway = FakeGateway(
        [
            _tool_call("ask_user", {"question": "Need more detail?"}),
            _tool_call("ask_user", {"question": "Still need more detail?"}),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "orchestrator_tool_calling_enabled": True,
            "orchestrator_tool_max_iterations": 1,
            "orchestrator_tool_gateway": gateway,
            "managed_agent_ids": ["codex-helper"],
            "sub_adapters": {},
        },
    )

    assert chunks[-1].event_type == "error"
    assert chunks[-1].error_code == "loop_max_iterations"
