"""Tests for shared single-agent requirement alignment."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.api.v1.messages as messages_api
from app.agents.orchestrator.clarification import CLARIFICATION_STATE_PREFIX
from app.agents.requirement_alignment import maybe_handle_single_agent_requirement_alignment
from app.agents.types import ChatMessage

pytestmark = pytest.mark.asyncio


async def test_single_agent_strict_alignment_returns_clarification_block() -> None:
    result = await maybe_handle_single_agent_requirement_alignment(
        agent_id="claude-code",
        messages=[ChatMessage(role="user", content="帮我做一个任务管理网站，包含前后端")],
        config={
            "turn_options": {"requirement_alignment": "strict"},
            "requirement_alignment_llm_enabled": False,
        },
    )

    assert result.handled
    assert result.stream is not None
    chunks = [chunk async for chunk in result.stream]
    clarification = next(chunk for chunk in chunks if chunk.block_type == "clarification")
    assert clarification.agent_id == "claude-code"
    assert clarification.metadata is not None
    assert clarification.metadata["mode"] == "requirement_alignment"
    assert clarification.metadata["title"] == "需求对齐"
    assert chunks[-1].event_type == "done"
    assert chunks[-1].agent_id == "claude-code"


async def test_single_agent_alignment_confirmation_augments_runtime_messages() -> None:
    state = {
        "mode": "requirement_alignment",
        "title": "需求对齐",
        "status": "waiting",
        "current_question": {
            "id": "scope",
            "question": "确认交付边界？",
            "recommended_answer": "生成 planning.md、前端文件和 review.md。",
            "status": "pending",
        },
        "questions": [
            {
                "id": "scope",
                "question": "确认交付边界？",
                "recommended_answer": "生成 planning.md、前端文件和 review.md。",
                "status": "pending",
            }
        ],
        "metadata": {
            "original_request": "帮我做一个任务管理网站",
            "question_count": 1,
            "max_questions": 3,
            "agent_id": "claude-code",
        },
    }
    result = await maybe_handle_single_agent_requirement_alignment(
        agent_id="claude-code",
        messages=[
            ChatMessage(role="user", content="帮我做一个任务管理网站"),
            ChatMessage(
                role="assistant",
                content=f"{CLARIFICATION_STATE_PREFIX}{json.dumps(state, ensure_ascii=False)}",
            ),
            ChatMessage(role="user", content="按这个做"),
        ],
        config={"turn_options": {"requirement_alignment": "strict"}},
    )

    assert not result.handled
    assert result.leading_chunks
    assert result.messages is not None
    assert "Clarification resolved before planning" in result.messages[-1].content
    assert "帮我做一个任务管理网站" in result.messages[-1].content
    assert "按这个做" in result.messages[-1].content


async def test_single_agent_alignment_skips_orchestrator_child_task_runtime() -> None:
    result = await maybe_handle_single_agent_requirement_alignment(
        agent_id="claude-code",
        messages=[ChatMessage(role="user", content="实现 Orchestrator 分配的子任务")],
        config={
            "turn_options": {"requirement_alignment": "strict"},
            "runtime_context": {"orchestrator_task_id": "task-1"},
        },
    )

    assert not result.handled
    assert result.messages is None
    assert result.leading_chunks == ()


async def test_single_agent_alignment_skips_small_talk() -> None:
    result = await maybe_handle_single_agent_requirement_alignment(
        agent_id="claude-code",
        messages=[ChatMessage(role="user", content="你是谁？")],
        config={"turn_options": {"requirement_alignment": "strict"}},
    )

    assert not result.handled


async def test_group_strict_alignment_target_resolves_to_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated: list[list[str]] = []

    async def fake_validate(_db: object, _user_id: object, agent_ids: list[str]) -> None:
        validated.append(agent_ids)

    monkeypatch.setattr(messages_api, "_validate_visible_agent_ids", fake_validate)

    target = await messages_api._resolve_target_agent_id(
        object(),
        uuid4(),
        SimpleNamespace(mode="group", agent_ids=["orchestrator", "claude-code"]),
        "claude-code",
        request_text="@claude-code 请先对齐需求",
        requirement_alignment="strict",
    )

    assert target == "orchestrator"
    assert validated == [["orchestrator"]]
