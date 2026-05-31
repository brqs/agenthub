"""Tests for Orchestrator platform preview/browser quality gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.orchestrator import OrchestratorAdapter
from app.agents.orchestrator.tools import OrchestratorToolResult
from app.agents.types import ChatMessage
from tests.orchestrator_fakes import (
    FakeSubAdapter,
    FakeWorkspaceWriterAdapter,
    _collect,
    _task,
    _text_chunks,
)


class FakePlatformToolExecutor:
    def __init__(self, verify_passes: list[bool]) -> None:
        self.verify_passes = verify_passes
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
                "issues": [] if passed else [{"code": "console_error", "message": "boom"}],
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
        return OrchestratorToolResult(
            status="error",
            output="unexpected tool",
            error_code="tool_not_allowed",
        )


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
    executor = FakePlatformToolExecutor([False, True])
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
        "verify_web_preview",
    ]
    assert [
        chunk.tool_name for chunk in chunks if chunk.event_type == "tool_call"
    ] == [
        "start_workspace_preview",
        "verify_web_preview",
        "verify_web_preview",
    ]
    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert "Browser quality verification passed" in text
    assert "浏览器验证问题" in repair.received_messages[-1].content


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
        "verify_web_preview",
    ]
