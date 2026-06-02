"""Tests for Orchestrator platform preview/browser quality gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.agents.orchestrator import OrchestratorAdapter
from app.agents.orchestrator.tools import OrchestratorToolResult
from app.agents.orchestrator.types import SubTask, TaskResult
from app.agents.types import ChatMessage
from tests.orchestrator_fakes import (
    FakeSubAdapter,
    FakeWorkspaceWriterAdapter,
    _collect,
    _task,
    _text_chunks,
)


class FakePlatformToolExecutor:
    def __init__(
        self,
        verify_passes: list[bool],
        *,
        issue_code: str = "console_error",
    ) -> None:
        self.verify_passes = verify_passes
        self.issue_code = issue_code
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> OrchestratorToolResult:
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "start_workspace_preview":
            return OrchestratorToolResult(
                status="ok",
                output=json.dumps(
                    {
                        "status": "running",
                        "entry_path": arguments["entry_path"],
                        "port": arguments.get("requested_port", 8082),
                        "url": "http://127.0.0.1:8082/index.html",
                    }
                ),
            )
        if tool_name == "verify_web_preview":
            passed = self.verify_passes.pop(0)
            report = {
                "passed": passed,
                "issues": [] if passed else [{"code": self.issue_code, "message": "boom"}],
                "screenshots": {"desktop": "/tmp/desktop.png", "mobile": "/tmp/mobile.png"},
                "console_errors": [] if passed else ["boom"],
                "page_errors": [],
                "failed_requests": [],
                "checks": {"no_console_errors": passed},
                "duration_ms": 1,
            }
            return OrchestratorToolResult(
                status="ok" if passed else "error",
                output=json.dumps(report),
                error_code=None if passed else "browser_verification_failed",
            )
        if tool_name == "create_deployment":
            kind = arguments["kind"]
            payload = {
                "deployment_id": f"dep-{kind}",
                "kind": kind,
                "status": "not_supported" if kind == "container" else "published",
                "entry_path": arguments.get("entry_path"),
                "url": "http://127.0.0.1:8082/index.html"
                if kind == "static_site"
                else None,
                "download_url": None,
                "error": "Container deployment is not supported"
                if kind == "container"
                else None,
                "logs_preview": "deployment log",
                "size_bytes": None,
            }
            payload["status_card"] = {
                "type": "deployment_status",
                **payload,
            }
            return OrchestratorToolResult(status="ok", output=json.dumps(payload))
        if tool_name == "package_workspace_source":
            payload = {
                "deployment_id": "dep-source",
                "kind": "source_zip",
                "status": "published",
                "entry_path": None,
                "url": None,
                "download_url": "/api/v1/workspaces/x/deployments/dep-source/download",
                "error": None,
                "logs_preview": "source log",
                "size_bytes": 123,
            }
            payload["status_card"] = {
                "type": "deployment_status",
                **payload,
            }
            return OrchestratorToolResult(status="ok", output=json.dumps(payload))
        return OrchestratorToolResult(
            status="error",
            output="unexpected tool",
            error_code="tool_not_allowed",
        )


class FakeMemoryWriter:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.events: list[tuple[str, dict[str, Any] | None]] = []

    async def start_run(
        self,
        *,
        user_request: str,
        plan_source: str,
        tasks: list[SubTask],
    ) -> UUID:
        _ = (user_request, plan_source, tasks)
        return self.run_id

    async def record_task_planned(self, *, run_id: UUID, task: SubTask) -> None:
        _ = (run_id, task)

    async def record_task_started(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        agent_id: str,
        attempt_index: int,
    ) -> None:
        _ = (run_id, task, agent_id, attempt_index)

    async def record_task_result(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        result: TaskResult,
    ) -> None:
        _ = (run_id, task, result)

    async def record_event(
        self,
        *,
        run_id: UUID,
        event_type: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        _ = (run_id, task_id, agent_id)
        self.events.append((event_type, payload))

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        final_summary: str,
    ) -> None:
        _ = (run_id, status, final_summary)

    async def cancel_active_run(self) -> None:
        pass


async def test_quality_gate_repairs_failed_browser_verification(
    tmp_path: Path,
) -> None:
    generator = FakeWorkspaceWriterAdapter(
        "claude-code",
        _text_chunks("Created index.html"),
        "index.html",
        "<!doctype html><html><body><h1>bad</h1></body></html>",
    )
    repair = FakeWorkspaceWriterAdapter(
        "codex-helper",
        _text_chunks("Fixed index.html"),
        "index.html",
        "<!doctype html><html><body><h1>任务 代码 Diff 预览 按钮 移动</h1></body></html>",
    )
    executor = FakePlatformToolExecutor(
        [False, True],
        issue_code="mobile_no_horizontal_overflow",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 做一个前端网页演示，部署在端口8082，"
                    "并完成浏览器质量验收"
                ),
            )
        ],
        workspace_path=tmp_path,
        config={
            "react_enabled": False,
            "tasks": [
                _task(
                    "create-demo",
                    "claude-code",
                    "Create demo",
                    "Create index.html",
                    expected_output="index.html",
                )
            ],
            "managed_agent_ids": ["claude-code", "codex-helper"],
            "sub_adapters": {
                "claude-code": generator,
                "codex-helper": repair,
            },
            "orchestrator_platform_tool_executor": executor,
            "orchestrator_quality_max_repair_rounds": 2,
        },
    )

    assert chunks[-1].event_type == "done"
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "claude-code",
        "codex-helper",
    ]
    assert [call[0] for call in executor.calls] == [
        "start_workspace_preview",
        "verify_web_preview",
        "start_workspace_preview",
        "verify_web_preview",
        "create_deployment",
    ]
    assert [
        chunk.tool_name for chunk in chunks if chunk.event_type == "tool_call"
    ] == [
        "start_workspace_preview",
        "verify_web_preview",
        "start_workspace_preview",
        "verify_web_preview",
        "create_deployment",
    ]
    assert any(chunk.block_type == "deployment_status" for chunk in chunks)
    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert "Browser quality verification passed" in text
    assert "浏览器验证问题" in repair.received_messages[-1].content
    assert "mobile_no_horizontal_overflow" in repair.received_messages[-1].content
    assert "overflow-wrap:anywhere" in repair.received_messages[-1].content


async def test_quality_gate_creates_missing_frontend_artifacts_before_preview(
    tmp_path: Path,
) -> None:
    generator = FakeSubAdapter("claude-code", _text_chunks("No files created"))
    repair = FakeWorkspaceWriterAdapter(
        "codex-helper",
        _text_chunks("Created missing index.html"),
        "index.html",
        "<!doctype html><html><body><button>任务 代码 Diff 预览 按钮 移动</button></body></html>",
    )
    executor = FakePlatformToolExecutor([True])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="@orchestrator 做一个前端网页演示，部署在端口8082，完成浏览器质量验收",
            )
        ],
        workspace_path=tmp_path,
        config={
            "react_enabled": False,
            "tasks": [
                _task(
                    "create-demo",
                    "claude-code",
                    "Create demo",
                    "Create the demo.",
                )
            ],
            "managed_agent_ids": ["claude-code", "codex-helper"],
            "sub_adapters": {
                "claude-code": generator,
                "codex-helper": repair,
            },
            "orchestrator_platform_tool_executor": executor,
            "orchestrator_quality_max_repair_rounds": 1,
        },
    )

    assert chunks[-1].event_type == "done"
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "claude-code",
        "codex-helper",
    ]
    assert [call[0] for call in executor.calls] == [
        "start_workspace_preview",
        "verify_web_preview",
        "create_deployment",
    ]
    assert executor.calls[0][1]["entry_path"] == "index.html"
    assert "No HTML entry file was found" in repair.received_messages[-1].content


async def test_quality_gate_fails_after_repair_limit(tmp_path: Path) -> None:
    generator = FakeWorkspaceWriterAdapter(
        "claude-code",
        _text_chunks("Created index.html"),
        "index.html",
        "<!doctype html><html><body><h1>bad</h1></body></html>",
    )
    repair = FakeWorkspaceWriterAdapter(
        "codex-helper",
        _text_chunks("Attempted fix"),
        "index.html",
        "<!doctype html><html><body><script>throw new Error('bad')</script></body></html>",
    )
    executor = FakePlatformToolExecutor([False, False])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="@orchestrator 做一个前端网页演示，部署在端口8082，完成浏览器质量验收",
            )
        ],
        workspace_path=tmp_path,
        config={
            "react_enabled": False,
            "tasks": [
                _task(
                    "create-demo",
                    "claude-code",
                    "Create demo",
                    "Create index.html",
                    expected_output="index.html",
                )
            ],
            "managed_agent_ids": ["claude-code", "codex-helper"],
            "sub_adapters": {
                "claude-code": generator,
                "codex-helper": repair,
            },
            "orchestrator_platform_tool_executor": executor,
            "orchestrator_quality_max_repair_rounds": 1,
        },
    )

    assert chunks[-1].event_type == "error"
    assert chunks[-1].error_code == "browser_verification_failed"
    assert [call[0] for call in executor.calls] == [
        "start_workspace_preview",
        "verify_web_preview",
        "start_workspace_preview",
        "verify_web_preview",
    ]


async def test_quality_gate_packages_source_and_container_placeholder(
    tmp_path: Path,
) -> None:
    generator = FakeWorkspaceWriterAdapter(
        "claude-code",
        _text_chunks("Created index.html"),
        "index.html",
        "<!doctype html><html><body><h1>任务 代码 Diff 预览</h1></body></html>",
    )
    executor = FakePlatformToolExecutor([True])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 做一个前端网页演示，部署在端口8082，"
                    "返回部署状态卡片，并打包源码下载，尝试容器化部署"
                ),
            )
        ],
        workspace_path=tmp_path,
        config={
            "react_enabled": False,
            "tasks": [
                _task(
                    "create-demo",
                    "claude-code",
                    "Create demo",
                    "Create index.html",
                    expected_output="index.html",
                )
            ],
            "managed_agent_ids": ["claude-code"],
            "sub_adapters": {"claude-code": generator},
            "orchestrator_platform_tool_executor": executor,
        },
    )

    assert chunks[-1].event_type == "done"
    assert [call[0] for call in executor.calls] == [
        "start_workspace_preview",
        "verify_web_preview",
        "create_deployment",
        "package_workspace_source",
        "create_deployment",
    ]
    assert [call[1].get("kind") for call in executor.calls if call[0] == "create_deployment"] == [
        "static_site",
        "container",
    ]
    assert sum(chunk.block_type == "deployment_status" for chunk in chunks) == 3


async def test_quality_gate_records_evaluation_events(tmp_path: Path) -> None:
    generator = FakeWorkspaceWriterAdapter(
        "claude-code",
        _text_chunks("Created index.html"),
        "index.html",
        "<!doctype html><html><body><h1>任务 代码 Diff 预览</h1></body></html>",
    )
    executor = FakePlatformToolExecutor([True])
    writer = FakeMemoryWriter()
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="@orchestrator 做一个前端网页演示，部署在端口8082，完成浏览器质量验收",
            )
        ],
        workspace_path=tmp_path,
        config={
            "react_enabled": False,
            "tasks": [
                _task(
                    "create-demo",
                    "claude-code",
                    "Create demo",
                    "Create index.html",
                    expected_output="index.html",
                )
            ],
            "managed_agent_ids": ["claude-code"],
            "sub_adapters": {"claude-code": generator},
            "orchestrator_platform_tool_executor": executor,
            "orchestrator_memory_writer": writer,
        },
    )

    assert chunks[-1].event_type == "done"
    result_payloads = [
        payload for event_type, payload in writer.events if event_type == "evaluation_result"
    ]
    result_evaluators = [
        result["evaluator"]
        for payload in result_payloads
        if payload
        for result in payload["results"]
    ]
    assert "browser_preview_quality" in result_evaluators
    assert "deployment_health" in result_evaluators
