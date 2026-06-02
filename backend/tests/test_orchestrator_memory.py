"""Orchestrator structured memory tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.orchestrator.types import SubTask, TaskAttempt, TaskResult, TaskState
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.database import Base, SessionFactory, engine
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.orchestrator_memory import OrchestratorRun
from app.models.user import User
from app.services.orchestrator_memory import (
    OrchestratorMemoryStore,
    build_orchestrator_memory_context,
    inject_orchestrator_memory_context,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


class FakeSubAdapter(BaseAgentAdapter):
    provider = "fake"

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = (messages, system_prompt, config, workspace_path, tool_specs)
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta="Created orchestrator-memory-demo.html",
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)


class FakeWorkspaceWriterAdapter(FakeSubAdapter):
    def __init__(self, agent_id: str, write_path: str, content: str) -> None:
        super().__init__(agent_id=agent_id)
        self.write_path = write_path
        self.content = content

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if workspace_path is not None:
            (workspace_path / self.write_path).write_text(self.content, encoding="utf-8")
        async for chunk in super().stream(
            messages,
            system_prompt=system_prompt,
            config=config,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
        ):
            yield chunk


class FakeMemoryWriter:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.started = False
        self.task_started: list[tuple[str, str, int]] = []
        self.results: list[TaskResult] = []
        self.events: list[tuple[str, str | None, str | None, dict[str, object] | None]] = []
        self.finished: tuple[str, str] | None = None

    async def start_run(
        self,
        *,
        user_request: str,
        plan_source: str,
        tasks: list[SubTask],
    ) -> UUID:
        assert user_request
        assert plan_source == "LLM planner/config"
        assert len(tasks) == 1
        self.started = True
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
        assert run_id == self.run_id
        self.task_started.append((task.task_id, agent_id, attempt_index))

    async def record_task_result(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        result: TaskResult,
    ) -> None:
        _ = task
        assert run_id == self.run_id
        self.results.append(result)

    async def record_event(
        self,
        *,
        run_id: UUID,
        event_type: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        assert run_id == self.run_id
        self.events.append((event_type, task_id, agent_id, payload))

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        final_summary: str,
    ) -> None:
        assert run_id == self.run_id
        self.finished = (status, final_summary)

    async def cancel_active_run(self) -> None:
        pass


async def _create_conversation() -> tuple[UUID, UUID]:
    async with SessionFactory() as db:
        user = User(username=f"orch_mem_{uuid4().hex[:16]}", password_hash="hash")
        db.add(user)
        await db.flush()
        conversation = Conversation(
            user_id=user.id,
            title="Orchestrator memory",
            mode="group",
            agent_ids=["orchestrator", "codex-helper"],
        )
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            role="agent",
            agent_id="orchestrator",
            content=[],
            status="streaming",
        )
        db.add(message)
        await db.commit()
        return conversation.id, message.id


async def test_orchestrator_writer_receives_run_task_and_summary() -> None:
    writer = FakeMemoryWriter()
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")
    chunks = [
        chunk
        async for chunk in orchestrator.stream(
            messages=[ChatMessage(role="user", content="Build memory demo")],
            config={
                "sub_adapters": {"codex-helper": FakeSubAdapter("codex-helper")},
                "orchestrator_memory_writer": writer,
                "react_enabled": False,
                "tasks": [
                    {
                        "task_id": "create",
                        "agent_id": "codex-helper",
                        "title": "Create demo",
                        "instruction": "Create orchestrator-memory-demo.html",
                        "expected_output": "orchestrator-memory-demo.html",
                    }
                ],
            },
        )
    ]

    assert chunks[-1].event_type == "done"
    assert writer.started is True
    assert writer.task_started == [("create", "codex-helper", 1)]
    assert len(writer.results) == 1
    assert writer.results[0].final_state.value == "succeeded"
    assert writer.finished is not None
    assert writer.finished[0] == "done"
    assert "Execution summary" in writer.finished[1]


async def test_orchestrator_writer_receives_evaluation_events(tmp_path: Path) -> None:
    writer = FakeMemoryWriter()
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")
    chunks = [
        chunk
        async for chunk in orchestrator.stream(
            messages=[ChatMessage(role="user", content="Build memory report")],
            workspace_path=tmp_path,
            config={
                "sub_adapters": {
                    "codex-helper": FakeWorkspaceWriterAdapter(
                        "codex-helper",
                        "report.md",
                        "",
                    )
                },
                "orchestrator_memory_writer": writer,
                "react_enabled": False,
                "tasks": [
                    {
                        "task_id": "create",
                        "agent_id": "codex-helper",
                        "title": "Create report",
                        "instruction": "Create report.md",
                        "expected_output": "report.md",
                    }
                ],
            },
        )
    ]

    assert chunks[-1].event_type == "done"
    event_types = [event[0] for event in writer.events]
    assert "evaluation_started" in event_types
    assert "evaluation_result" in event_types
    assert "reflection_created" in event_types
    assert "evaluation_finished" in event_types
    result_payload = next(
        event[3] for event in writer.events if event[0] == "evaluation_result"
    )
    assert result_payload is not None
    assert any(
        result["evaluator"] == "document_quality" and result["status"] == "failed"
        for result in result_payload["results"]
    )


async def test_memory_store_formats_recent_runs_before_latest_user_request() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        task = SubTask(
            task_id="create",
            agent_id="codex-helper",
            title="Create HTML",
            instruction="Create orchestrator-memory-demo.html",
            expected_output="orchestrator-memory-demo.html",
        )
        run_id = await store.start_run(
            user_request="Create HTML demo",
            plan_source="LLM planner/config",
            tasks=[task],
        )
        result = TaskResult(
            task_id=task.task_id,
            title=task.title,
            final_state=TaskState.SUCCEEDED,
        )
        result.attempts.append(
            TaskAttempt(
                attempt_index=1,
                agent_id="codex-helper",
                state=TaskState.SUCCEEDED,
                text_preview="Created orchestrator-memory-demo.html",
                artifact_paths=["orchestrator-memory-demo.html"],
            )
        )
        await store.record_task_result(run_id=run_id, task=task, result=result)
        await store.finish_run(
            run_id=run_id,
            status="done",
            final_summary="Execution summary\n- succeeded",
        )
        await db.commit()

    async with SessionFactory() as db:
        run = await db.get(OrchestratorRun, run_id)
        memory = await build_orchestrator_memory_context(db, conversation_id)

    assert run is not None
    assert run.status == "done"
    assert memory is not None
    assert "Previous Orchestrator structured memory" in memory.content
    assert "orchestrator-memory-demo.html" in memory.content

    messages = [
        ChatMessage(role="system", content="earlier"),
        ChatMessage(role="user", content="continue this task"),
    ]
    injected = inject_orchestrator_memory_context(messages, memory)

    assert injected[-1].content == "continue this task"
    assert injected[-2].content.startswith("Previous Orchestrator structured memory")
