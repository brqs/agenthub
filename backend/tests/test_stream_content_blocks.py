"""Tests for SSE stream persistence of diff and web_preview ContentBlocks."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.types import StreamChunk
from app.api.v1.stream_accumulator import StreamContentAccumulator
from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message
from app.schemas.message import MessageOut
from app.services.context.compression import blocks_to_text

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_stream_accumulator_persists_deployment_status_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="deployment_status",
            metadata={
                "deployment_id": "deployment-1",
                "kind": "static_site",
                "status": "published",
                "title": "Static site deployment",
                "url": "http://127.0.0.1:8082/index.html",
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    assert accumulator.to_list() == [
        {
            "type": "deployment_status",
            "deployment_id": "deployment-1",
            "kind": "static_site",
            "status": "published",
            "title": "Static site deployment",
            "url": "http://127.0.0.1:8082/index.html",
        }
    ]


async def test_stream_accumulator_persists_file_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="file",
            agent_id="agent-a",
            metadata={
                "path": "docs/report.md",
                "filename": "report.md",
                "url": "/api/v1/workspaces/conversation-1/files/docs/report.md",
                "size": 42,
                "mime_type": "text/markdown",
                "artifact_kind": "document",
                "preview_text": "# Report",
                "preview_truncated": False,
                "metadata": {"section_count": 1},
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    assert accumulator.to_list() == [
        {
            "type": "file",
            "agent_id": "agent-a",
            "path": "docs/report.md",
            "filename": "report.md",
            "url": "/api/v1/workspaces/conversation-1/files/docs/report.md",
            "size": 42,
            "mime_type": "text/markdown",
            "artifact_kind": "document",
            "preview_text": "# Report",
            "preview_truncated": False,
            "metadata": {"section_count": 1},
        }
    ]


async def test_stream_accumulator_persists_task_card_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="task_card",
            agent_id="orchestrator",
            metadata={
                "title": "Orchestrator plan",
                "tasks": [
                    {
                        "id": "task-a",
                        "agent_id": "claude-code",
                        "title": "Generate page",
                        "status": "running",
                    },
                    {
                        "id": "task-b",
                        "agent_id": "codex-helper",
                        "title": "Review code",
                        "status": "pending",
                    },
                ],
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    assert accumulator.to_list() == [
        {
            "type": "task_card",
            "agent_id": "orchestrator",
            "title": "Orchestrator plan",
            "tasks": [
                {
                    "id": "task-a",
                    "agent_id": "claude-code",
                    "title": "Generate page",
                    "status": "running",
                },
                {
                    "id": "task-b",
                    "agent_id": "codex-helper",
                    "title": "Review code",
                    "status": "pending",
                },
            ],
        }
    ]


async def test_stream_chunk_and_accumulator_persist_process_block() -> None:
    chunk = StreamChunk(
        event_type="block_start",
        block_index=0,
        block_type="process",
        agent_id="orchestrator",
        metadata={
            "title": "思考与执行",
            "status": "running",
            "default_collapsed": False,
            "steps": [],
            "metadata": {"source": "orchestrator_process"},
        },
    )
    assert '"block_type":"process"' in chunk.model_dump_json(exclude_none=True)

    accumulator = StreamContentAccumulator()
    accumulator.feed(chunk)
    accumulator.feed(
        StreamChunk(
            event_type="delta",
            block_index=0,
            metadata={
                "process_delta": {
                    "op": "upsert_step",
                    "step": {
                        "id": "summary",
                        "label": "整理公开摘要",
                        "kind": "summary",
                        "status": "done",
                        "detail": "已整理。",
                    },
                }
            },
        )
    )
    accumulator.feed(
        StreamChunk(
            event_type="delta",
            block_index=0,
            metadata={
                "process_delta": {
                    "op": "set_summary",
                    "status": "partial",
                    "summary": "过程部分完成，下面的回答包含需要注意的事项。",
                }
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    assert accumulator.to_list() == [
        {
            "type": "process",
            "agent_id": "orchestrator",
            "title": "思考与执行",
            "status": "partial",
            "default_collapsed": False,
            "summary": "过程部分完成，下面的回答包含需要注意的事项。",
            "steps": [
                {
                    "id": "summary",
                    "label": "整理公开摘要",
                    "kind": "summary",
                    "status": "done",
                    "detail": "已整理。",
                }
            ],
            "metadata": {"source": "orchestrator_process"},
        }
    ]


async def test_stream_accumulator_persists_clarification_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="clarification",
            agent_id="orchestrator",
            metadata={
                "mode": "grill_me",
                "title": "需求追问",
                "status": "waiting",
                "current_question": {
                    "id": "audience_goal",
                    "question": "目标用户是谁？",
                    "reason": "先锁定使用场景。",
                    "recommended_answer": "普通用户，桌面和移动端都可用。",
                    "options": ["使用推荐答案"],
                    "status": "pending",
                },
                "questions": [],
                "metadata": {"original_request": "做一个网页游戏"},
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    assert accumulator.to_list() == [
        {
            "type": "clarification",
            "agent_id": "orchestrator",
            "mode": "grill_me",
            "title": "需求追问",
            "status": "waiting",
            "current_question": {
                "id": "audience_goal",
                "question": "目标用户是谁？",
                "reason": "先锁定使用场景。",
                "recommended_answer": "普通用户，桌面和移动端都可用。",
                "options": ["使用推荐答案"],
                "status": "pending",
            },
            "questions": [],
            "metadata": {"original_request": "做一个网页游戏"},
        }
    ]


async def test_blocks_to_text_preserves_full_clarification_state() -> None:
    text = blocks_to_text(
        [
            {
                "type": "clarification",
                "mode": "auto",
                "title": "确认澄清方向",
                "status": "waiting",
                "current_question": {
                    "id": "topic_route",
                    "question": "继续当前需求还是切换？",
                    "recommended_answer": "继续澄清当前需求",
                    "options": ["继续澄清当前需求", "切换到新需求"],
                    "status": "pending",
                },
                "questions": [
                    {
                        "id": "delivery_defaults",
                        "question": "交付边界？",
                        "status": "answered",
                        "answer": "静态前端产物",
                    },
                    {
                        "id": "topic_route",
                        "question": "继续当前需求还是切换？",
                        "status": "pending",
                    },
                ],
                "summary": "等待方向确认。",
                "metadata": {
                    "original_request": "项目 A 做网页游戏",
                    "route_pending_user_request": "项目 B 的登录体验怎么改？",
                },
            }
        ]
    )

    payload = json.loads(text.removeprefix("[Clarification state] "))
    assert payload["current_question"]["id"] == "topic_route"
    assert payload["current_question"]["options"] == ["继续澄清当前需求", "切换到新需求"]
    assert payload["questions"][0]["answer"] == "静态前端产物"
    assert payload["questions"][1]["id"] == "topic_route"
    assert payload["metadata"]["route_pending_user_request"] == "项目 B 的登录体验怎么改？"
    assert payload["question_id"] == "topic_route"


async def test_stream_accumulator_persists_workflow_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="workflow",
            agent_id="codex-helper",
            metadata={"format": "yaml", "path": "workflow.yaml"},
        )
    )
    accumulator.feed(
        StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta=(
                "version: '1'\n"
                "name: Launch Flow\n"
                "nodes:\n"
                "  - id: start\n"
                "    type: trigger\n"
                "  - id: publish\n"
                "    type: action\n"
                "edges:\n"
                "  - source: start\n"
                "    target: publish\n"
            ),
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    blocks = accumulator.to_list()

    assert blocks[0]["type"] == "workflow"
    assert blocks[0]["agent_id"] == "codex-helper"
    assert blocks[0]["path"] == "workflow.yaml"
    assert blocks[0]["name"] == "Launch Flow"
    assert blocks[0]["validation_status"] == "passed"
    assert blocks[0]["runtime_status"] == "ready"
    assert blocks[0]["dry_run_status"] == "not_supported"
    assert [node["id"] for node in blocks[0]["nodes"]] == ["start", "publish"]
    assert blocks[0]["edges"] == [{"source": "start", "target": "publish"}]


async def test_stream_accumulator_upgrades_json_code_to_workflow_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="code",
            metadata={"language": "json"},
        )
    )
    accumulator.feed(
        StreamChunk(
            event_type="delta",
            block_index=0,
            code_delta=(
                '{"version":"1","name":"JSON Flow",'
                '"nodes":[{"id":"n1","type":"trigger"}],"edges":[]}'
            ),
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    blocks = accumulator.to_list()

    assert blocks[0]["type"] == "workflow"
    assert blocks[0]["format"] == "json"
    assert blocks[0]["name"] == "JSON Flow"
    assert blocks[0]["validation_status"] == "passed"


async def test_stream_accumulator_extracts_workflow_from_text_fence() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="text",
            agent_id="claude-code",
        )
    )
    accumulator.feed(
        StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta=(
                "Created p1-workflow.yaml\n\n"
                "```yaml\n"
                "version: '1'\n"
                "name: P1 Workflow E2E\n"
                "nodes:\n"
                "  - id: start\n"
                "    type: trigger\n"
                "  - id: review\n"
                "    type: action\n"
                "edges:\n"
                "  - source: start\n"
                "    target: review\n"
                "```\n"
            ),
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    blocks = accumulator.to_list()

    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "workflow"
    assert blocks[1]["agent_id"] == "claude-code"
    assert blocks[1]["path"] == "p1-workflow.yaml"
    assert blocks[1]["name"] == "P1 Workflow E2E"
    assert blocks[1]["validation_status"] == "passed"
    assert blocks[1]["runtime_status"] == "ready"


async def test_stream_accumulator_keeps_regular_json_code_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="code",
            metadata={"language": "json"},
        )
    )
    accumulator.feed(StreamChunk(event_type="delta", block_index=0, code_delta='{"ok":true}'))
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    assert accumulator.to_list() == [
        {"type": "code", "language": "json", "code": '{"ok":true}'}
    ]


async def test_stream_accumulator_updates_task_card_from_agent_switch() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="task_card",
            metadata={
                "title": "Orchestrator plan",
                "tasks": [
                    {
                        "id": "task-a",
                        "agent_id": "claude-code",
                        "title": "Build HTML",
                        "status": "pending",
                    },
                    {
                        "id": "task-b",
                        "agent_id": "claude-code",
                        "title": "Review HTML",
                        "status": "pending",
                    },
                ],
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    accumulator.feed(
        StreamChunk(
            event_type="agent_switch",
            from_agent="orchestrator",
            to_agent="claude-code",
            task="Build HTML",
        )
    )
    assert accumulator.to_list()[0]["tasks"] == [
        {
            "id": "task-a",
            "agent_id": "claude-code",
            "title": "Build HTML",
            "status": "running",
        },
        {
            "id": "task-b",
            "agent_id": "claude-code",
            "title": "Review HTML",
            "status": "pending",
        },
    ]

    accumulator.feed(
        StreamChunk(
            event_type="agent_switch",
            from_agent="orchestrator",
            to_agent="claude-code",
            task="Review HTML",
        )
    )
    assert accumulator.to_list()[0]["tasks"] == [
        {
            "id": "task-a",
            "agent_id": "claude-code",
            "title": "Build HTML",
            "status": "done",
        },
        {
            "id": "task-b",
            "agent_id": "claude-code",
            "title": "Review HTML",
            "status": "running",
        },
    ]


async def test_stream_accumulator_finalizes_running_task_cards() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="task_card",
            metadata={
                "title": "Orchestrator plan",
                "tasks": [
                    {
                        "id": "task-a",
                        "agent_id": "claude-code",
                        "title": "Build HTML",
                        "status": "pending",
                    }
                ],
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))
    accumulator.feed(
        StreamChunk(
            event_type="agent_switch",
            from_agent="orchestrator",
            to_agent="claude-code",
            task="Build HTML",
        )
    )

    accumulator.finalize_task_cards(success=True)

    assert accumulator.to_list()[0]["tasks"][0]["status"] == "done"


async def test_stream_accumulator_marks_running_task_cards_error_on_failure() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="task_card",
            metadata={
                "title": "Orchestrator plan",
                "tasks": [
                    {
                        "id": "task-a",
                        "agent_id": "claude-code",
                        "title": "Build HTML",
                        "status": "running",
                    }
                ],
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    accumulator.finalize_task_cards(success=False)

    assert accumulator.to_list()[0]["tasks"][0]["status"] == "error"


async def test_stream_accumulator_marks_running_blocks_interrupted() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="task_card",
            metadata={
                "title": "Orchestrator plan",
                "tasks": [
                    {
                        "id": "task-a",
                        "agent_id": "claude-code",
                        "title": "Build HTML",
                        "status": "running",
                    },
                    {
                        "id": "task-b",
                        "agent_id": "claude-code",
                        "title": "Review HTML",
                        "status": "done",
                    },
                ],
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=1,
            block_type="process",
            metadata={
                "title": "Execution",
                "status": "running",
                "steps": [
                    {"label": "Plan", "kind": "planning", "status": "done"},
                    {"label": "Run", "kind": "dispatch", "status": "running"},
                ],
            },
        )
    )

    accumulator.finalize_interrupted()
    task_card, process = accumulator.to_list()

    assert task_card["tasks"][0]["status"] == "interrupted"
    assert task_card["tasks"][1]["status"] == "done"
    assert process["status"] == "interrupted"
    assert process["steps"][0]["status"] == "done"
    assert process["steps"][1]["status"] == "interrupted"


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'test-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"user_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent(*, user_id: UUID | None = None, is_builtin: bool = True) -> str:
    agent_id = f"test-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                user_id=user_id,
                name="Test Agent",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["testing"],
                system_prompt=None,
                config={},
                is_builtin=is_builtin,
            )
        )
        await db.commit()
    return agent_id


async def _ensure_builtin_agent(agent_id: str, *, name: str | None = None) -> str:
    async with SessionFactory() as db:
        existing = await db.get(Agent, agent_id)
        if existing is None:
            db.add(
                Agent(
                    id=agent_id,
                    user_id=None,
                    name=name or agent_id,
                    provider="builtin",
                    avatar_url=f"/avatars/{agent_id}.png",
                    capabilities=["testing"],
                    system_prompt=None,
                    config={},
                    is_builtin=True,
                )
            )
            await db.commit()
    return agent_id


async def _create_conversation(
    client: AsyncClient,
    headers: dict[str, str],
    agent_ids: list[str],
    *,
    mode: str = "single",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "B2 content block test", "mode": mode, "agent_ids": agent_ids},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _send_message(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
    target_agent_id: str | None = None,
    content_text: str = "hello",
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": content_text}]}
    if target_agent_id is not None:
        payload["target_agent_id"] = target_agent_id
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_accumulator_persists_text_and_code_agent_id() -> None:
    accumulator = StreamContentAccumulator()

    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="text",
            agent_id="claude-code",
        )
    )
    accumulator.feed(StreamChunk(event_type="delta", block_index=0, text_delta="hello"))
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=1,
            block_type="code",
            metadata={"language": "python", "agent_id": "codex-helper"},
        )
    )
    accumulator.feed(StreamChunk(event_type="delta", block_index=1, code_delta="print(1)"))
    accumulator.feed(StreamChunk(event_type="block_end", block_index=1))

    blocks = accumulator.to_list()

    assert blocks[0] == {
        "type": "text",
        "agent_id": "claude-code",
        "text": "hello",
    }
    assert blocks[1] == {
        "type": "code",
        "agent_id": "codex-helper",
        "language": "python",
        "code": "print(1)",
    }


async def test_accumulator_preserves_diff_agent_id_after_finalize() -> None:
    accumulator = StreamContentAccumulator()

    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="diff",
            metadata={"filename": "changes.diff", "agent_id": "opencode-helper"},
        )
    )
    accumulator.feed(
        StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n",
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    blocks = accumulator.to_list()

    assert blocks[0]["type"] == "diff"
    assert blocks[0]["agent_id"] == "opencode-helper"
    assert blocks[0]["filename"] == "app.py"
    assert "old" in blocks[0]["before"]
    assert "new" in blocks[0]["after"]


async def test_accumulator_preserves_tool_call_agent_id_after_result() -> None:
    accumulator = StreamContentAccumulator()

    accumulator.feed(
        StreamChunk(
            event_type="tool_call",
            call_id="call-1",
            tool_name="write_file",
            tool_arguments={"path": "index.html"},
            agent_id="claude-code",
        )
    )
    accumulator.feed(
        StreamChunk(
            event_type="tool_result",
            call_id="call-1",
            tool_status="ok",
            tool_output="wrote file",
            agent_id="orchestrator",
        )
    )

    blocks = accumulator.to_list()

    assert blocks == [
        {
            "type": "tool_call",
            "agent_id": "claude-code",
            "call_id": "call-1",
            "tool_name": "write_file",
            "arguments": {"path": "index.html"},
            "status": "ok",
            "output_preview": "wrote file",
            "output_truncated": False,
        }
    ]


async def test_message_out_serializes_block_agent_id_and_legacy_blocks() -> None:
    message = MessageOut(
        id=uuid4(),
        conversation_id=uuid4(),
        role="agent",
        agent_id="orchestrator",
        content=[
            {"type": "text", "text": "legacy"},
            {
                "type": "tool_call",
                "agent_id": "claude-code",
                "call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {},
                "status": "ok",
            },
            {
                "type": "workflow",
                "name": "Flow",
                "definition": {
                    "version": "1",
                    "name": "Flow",
                    "nodes": [{"id": "start", "type": "trigger"}],
                    "edges": [],
                },
                "nodes": [{"id": "start", "type": "trigger"}],
                "edges": [],
                "validation_status": "passed",
                "runtime_status": "ready",
                "dry_run_status": "not_supported",
                "health_status": "passed",
            },
            {
                "type": "process",
                "agent_id": "orchestrator",
                "title": "思考与执行",
                "status": "done",
                "default_collapsed": False,
                "steps": [
                    {
                        "label": "直接回答",
                        "kind": "routing",
                        "status": "done",
                    }
                ],
                "summary": "过程已完成，下面是最终回答。",
                "metadata": {"source": "orchestrator_process"},
            },
        ],
        status="done",
        created_at=datetime.now(UTC),
    )

    body = message.model_dump(mode="json")

    assert body["content"][0]["agent_id"] is None
    assert body["content"][1]["agent_id"] == "claude-code"
    assert body["content"][2]["type"] == "workflow"
    assert body["content"][2]["name"] == "Flow"
    assert body["content"][3]["type"] == "process"
    assert body["content"][3]["steps"][0]["label"] == "直接回答"


async def test_openapi_includes_process_block_contract() -> None:
    app.openapi_schema = None
    schemas = app.openapi()["components"]["schemas"]

    assert "ProcessBlock" in schemas
    assert "ProcessStep" in schemas
    assert schemas["ProcessBlock"]["properties"]["type"].get("const") == "process"
    content_schema = schemas["MessageOut"]["properties"]["content"]["items"]
    refs = {item["$ref"] for item in content_schema["oneOf"]}
    assert "#/components/schemas/ProcessBlock" in refs


async def test_stream_persists_diff_block(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[Any]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="block_start",
                block_index=0,
                block_type="diff",
                agent_id="claude-code",
                metadata={"filename": "changes.diff"},
            )
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done"
    assert len(message.content) == 1
    assert message.content[0]["type"] == "diff"
    assert message.content[0]["agent_id"] == "claude-code"
    assert message.content[0]["filename"] == "app.py"
    assert "old" in message.content[0]["before"]
    assert "new" in message.content[0]["after"]


async def test_stream_persists_web_preview_block(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[Any]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="block_start",
                block_index=0,
                block_type="web_preview",
                metadata={"url": "https://example.com"},
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done"
    assert len(message.content) == 1
    assert message.content[0]["type"] == "web_preview"
    assert message.content[0]["url"] == "https://example.com"


async def test_orchestrator_group_stream_persists_child_agent_message(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    orchestrator_id = await _ensure_builtin_agent("orchestrator", name="Orchestrator")
    child_agent_id = await _ensure_builtin_agent(
        f"test-agent-{uuid4().hex}",
        name="Agent A",
    )
    conversation = await _create_conversation(
        client,
        headers,
        [orchestrator_id, child_agent_id],
        mode="group",
    )
    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        target_agent_id=orchestrator_id,
        content_text="Build a small demo",
    )
    agent_message_id = messages["agent_message"]["id"]

    class ChildAdapter(BaseAgentAdapter):
        provider = "fake"

        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start", agent_id=self.agent_id)
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="child agent built the demo",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)

    orchestrator = OrchestratorAdapter(
        agent_id=orchestrator_id,
        default_config={
            "react_enabled": False,
            "orchestrator_response_polish_enabled": False,
            "tasks": [
                {
                    "task_id": "task-a",
                    "agent_id": child_agent_id,
                    "title": "Build demo",
                    "instruction": "Build the demo.",
                }
            ],
            "sub_adapters": {child_agent_id: ChildAdapter(child_agent_id)},
        },
    )

    async def mock_get_adapter(agent_id: str, db: Any) -> OrchestratorAdapter:
        assert agent_id == orchestrator_id
        return orchestrator

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        sse_text = (await response.aread()).decode()

    async with SessionFactory() as db:
        stored_messages = (
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == UUID(conversation["id"]))
                    .order_by(Message.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    assert response.status_code == 200
    assert 'event: message_start' in sse_text
    assert 'event: message_done' in sse_text

    parent = next(message for message in stored_messages if str(message.id) == agent_message_id)
    child_messages = [
        message
        for message in stored_messages
        if message.role == "agent" and message.agent_id == child_agent_id
    ]
    assert len(child_messages) == 1
    child = child_messages[0]
    assert child.reply_to_id == UUID(messages["user_message"]["id"])
    assert child.status == "done"
    assert child.content[0]["type"] == "process"
    assert child.content[0]["agent_id"] == child_agent_id
    assert child.content[0]["status"] == "done"
    assert child.content[0]["default_collapsed"] is False
    assert child.content[0]["steps"][0]["agent_id"] == child_agent_id
    assert child.content[1:] == [
        {
            "type": "text",
            "agent_id": child_agent_id,
            "text": "child agent built the demo",
        }
    ]
    assert parent.status == "done"
    assert "child agent built the demo" not in str(parent.content)


async def test_orchestrator_group_parallel_stream_finishes_all_child_messages(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    orchestrator_id = await _ensure_builtin_agent("orchestrator", name="Orchestrator")
    agent_a_id = await _ensure_builtin_agent(f"test-agent-{uuid4().hex}", name="Agent A")
    agent_b_id = await _ensure_builtin_agent(f"test-agent-{uuid4().hex}", name="Agent B")
    conversation = await _create_conversation(
        client,
        headers,
        [orchestrator_id, agent_a_id, agent_b_id],
        mode="group",
    )
    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        target_agent_id=orchestrator_id,
        content_text="Build copy and styles in parallel",
    )
    agent_message_id = messages["agent_message"]["id"]

    class ChildAdapter(BaseAgentAdapter):
        provider = "fake"

        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start", agent_id=self.agent_id)
            yield StreamChunk(
                event_type="block_start",
                block_index=0,
                block_type="text",
                agent_id=self.agent_id,
            )
            await asyncio.sleep(0)
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta=f"{self.agent_id} completed assigned work",
                agent_id=self.agent_id,
            )
            yield StreamChunk(
                event_type="block_end",
                block_index=0,
                agent_id=self.agent_id,
            )
            yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)

    orchestrator = OrchestratorAdapter(
        agent_id=orchestrator_id,
        default_config={
            "react_enabled": False,
            "orchestrator_parallel_enabled": True,
            "orchestrator_parallel_max_concurrency": 2,
            "orchestrator_response_polish_enabled": False,
            "tasks": [
                {
                    "task_id": "task-a",
                    "agent_id": agent_a_id,
                    "title": "Build copy",
                    "instruction": "Build the copy.",
                },
                {
                    "task_id": "task-b",
                    "agent_id": agent_b_id,
                    "title": "Build styles",
                    "instruction": "Build the styles.",
                },
            ],
            "sub_adapters": {
                agent_a_id: ChildAdapter(agent_a_id),
                agent_b_id: ChildAdapter(agent_b_id),
            },
        },
    )

    async def mock_get_adapter(agent_id: str, db: Any) -> OrchestratorAdapter:
        assert agent_id == orchestrator_id
        return orchestrator

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        sse_text = (await response.aread()).decode()

    async with SessionFactory() as db:
        stored_messages = (
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == UUID(conversation["id"]))
                    .order_by(Message.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    assert response.status_code == 200
    assert sse_text.count("event: message_start") == 2
    assert sse_text.count("event: message_done") == 2
    assert "event: message_error" not in sse_text

    parent = next(message for message in stored_messages if str(message.id) == agent_message_id)
    child_messages = [
        message
        for message in stored_messages
        if message.role == "agent" and message.agent_id in {agent_a_id, agent_b_id}
    ]
    assert {message.agent_id for message in child_messages} == {agent_a_id, agent_b_id}
    assert {message.status for message in child_messages} == {"done"}
    assert all(
        message.reply_to_id == UUID(messages["user_message"]["id"])
        for message in child_messages
    )
    assert all(message.content for message in child_messages)
    assert parent.status == "done"
    assert "completed assigned work" not in str(parent.content)


async def test_stream_autostarts_platform_preview_for_deploy_request(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    preview_port = _free_port()
    monkeypatch.setattr(settings, "preview_enabled", True)
    monkeypatch.setattr(settings, "preview_port_start", preview_port)
    monkeypatch.setattr(settings, "preview_port_end", preview_port)
    monkeypatch.setattr(settings, "preview_public_base_url", "http://127.0.0.1")
    monkeypatch.setattr(settings, "preview_start_timeout_seconds", 5)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        content_text=f"请生成一个网页并部署到端口{preview_port}",
    )
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[Any]:
            assert workspace_path is not None
            (workspace_path / "index.html").write_text(
                "<!doctype html><title>Preview</title><h1>ok</h1>",
                encoding="utf-8",
            )
            yield StreamChunk(event_type="start")
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="Created index.html",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done", total_blocks=1)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        sse_text = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done", sse_text
    assert "start_workspace_preview" in sse_text
    assert any(
        block.get("type") == "tool_call"
        and block.get("tool_name") == "start_workspace_preview"
        and block.get("status") == "ok"
        for block in message.content
    )
    preview_blocks = [block for block in message.content if block.get("type") == "web_preview"]
    assert len(preview_blocks) == 1
    assert preview_blocks[0]["url"].startswith(f"http://127.0.0.1:{preview_port}/")

    preview = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/preview",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["entry_path"] == "index.html"
    assert preview.json()["port"] == preview_port

    await client.delete(
        f"/api/v1/workspaces/{conversation['id']}/preview",
        headers=headers,
    )


async def test_stream_preview_fallback_skips_when_formal_tool_called(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    preview_port = _free_port()
    monkeypatch.setattr(settings, "preview_enabled", True)
    monkeypatch.setattr(settings, "preview_port_start", preview_port)
    monkeypatch.setattr(settings, "preview_port_end", preview_port)
    monkeypatch.setattr(settings, "preview_public_base_url", "http://127.0.0.1")
    monkeypatch.setattr(settings, "preview_start_timeout_seconds", 5)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        content_text=f"请生成一个网页并部署到端口{preview_port}",
    )
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[Any]:
            assert workspace_path is not None
            (workspace_path / "index.html").write_text(
                "<!doctype html><title>Preview</title><h1>ok</h1>",
                encoding="utf-8",
            )
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="orch.quality.preview",
                tool_name="start_workspace_preview",
                tool_arguments={"entry_path": "index.html", "requested_port": preview_port},
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="orch.quality.preview",
                tool_status="ok",
                tool_output='{"status":"running","url":"http://127.0.0.1/fake"}',
            )
            yield StreamChunk(event_type="done", total_blocks=0)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        sse_text = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done", sse_text
    assert sse_text.count("start_workspace_preview") == 1
    assert "platform-preview-" not in sse_text
    preview = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/preview",
        headers=headers,
    )
    assert preview.status_code == 404


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
