"""Orchestrator structured memory tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

import app.services.orchestrator_memory as public_memory
from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.orchestrator.evaluation import EvaluationIssue, EvaluationResult
from app.agents.orchestrator.types import SubTask, TaskAttempt, TaskResult, TaskState
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.database import Base, SessionFactory, engine
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.orchestrator_memory import (
    OrchestratorRun,
    OrchestratorRunEvent,
    OrchestratorTask,
    OrchestratorTaskAttempt,
)
from app.models.user import User
from app.schemas.conversation import OrchestratorTaskAttemptOut, OrchestratorTaskOut
from app.services._orchestrator_memory.capability_v1 import (
    build_agent_capability_profile as internal_build_agent_capability_profile,
)
from app.services._orchestrator_memory.capability_v2 import (
    build_agent_capability_profile_v2 as internal_build_agent_capability_profile_v2,
)
from app.services._orchestrator_memory.context import (
    build_orchestrator_memory_context as internal_build_orchestrator_memory_context,
)
from app.services._orchestrator_memory.store import (
    OrchestratorMemoryStore as InternalOrchestratorMemoryStore,
)
from app.services.orchestrator_memory import (
    OrchestratorMemoryStore,
    build_agent_capability_profile,
    build_agent_capability_profile_v2,
    build_orchestrator_memory_context,
    inject_orchestrator_memory_context,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_orchestrator_memory_public_facade_reexports_stable_interfaces() -> None:
    assert public_memory.OrchestratorMemoryStore is InternalOrchestratorMemoryStore
    assert build_agent_capability_profile is internal_build_agent_capability_profile
    assert build_agent_capability_profile_v2 is internal_build_agent_capability_profile_v2
    assert (
        build_orchestrator_memory_context
        is internal_build_orchestrator_memory_context
    )
    assert set(public_memory.__all__) == {
        "AgentCapabilityProfileItem",
        "AgentCapabilityProfileV2",
        "AgentCapabilityProfileV2Item",
        "DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS",
        "DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS",
        "OrchestratorMemoryStore",
        "UserPreferenceMemory",
        "build_agent_capability_profile",
        "build_agent_capability_profile_v2",
        "build_orchestrator_memory_context",
        "get_orchestrator_run_detail",
        "inject_orchestrator_memory_context",
        "list_orchestrator_runs",
    }


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


async def _create_user_conversation() -> tuple[UUID, UUID, UUID]:
    async with SessionFactory() as db:
        user = User(username=f"orch_mem_user_{uuid4().hex[:16]}", password_hash="hash")
        db.add(user)
        await db.flush()
        conversation = Conversation(
            user_id=user.id,
            title="Orchestrator memory v2",
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
        return user.id, conversation.id, message.id


async def _create_conversation_for_user(user_id: UUID) -> tuple[UUID, UUID]:
    async with SessionFactory() as db:
        conversation = Conversation(
            user_id=user_id,
            title="Orchestrator memory v2 sibling",
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
    assert "Execution summary" not in "".join(chunk.text_delta or "" for chunk in chunks)


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
    assert injected[-2].content.startswith(
        "Agent capability profile v2 from recent user Orchestrator runs"
    )
    assert "Agent capability profile from recent Orchestrator runs" in injected[-2].content
    assert "Previous Orchestrator structured memory" in injected[-2].content


async def test_orchestrator_direct_answer_reports_latest_run_status() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        task = SubTask(
            task_id="frontend-build",
            agent_id="claude-code",
            title="Build static frontend demo artifacts",
            instruction="Create index.html",
            expected_output="index.html",
        )
        run_id = await store.start_run(
            user_request="Create a snake game",
            plan_source="frontend quality plan",
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
                agent_id="claude-code",
                state=TaskState.SUCCEEDED,
                text_preview="Created index.html",
                artifact_paths=["index.html", "styles.css", "app.js"],
            )
        )
        await store.record_task_result(run_id=run_id, task=task, result=result)
        await store.finish_run(
            run_id=run_id,
            status="done",
            final_summary="Execution summary\n- succeeded",
        )
        await db.commit()

        orchestrator = OrchestratorAdapter(agent_id="orchestrator")
        chunks = [
            chunk
            async for chunk in orchestrator.stream(
                messages=[
                    ChatMessage(
                        role="user",
                        content="\u4f60\u6267\u884c\u5b8c\u6210\u4e86\u5417",
                    )
                ],
                config={
                    "orchestrator_db_session": db,
                    "conversation_id": conversation_id,
                    "managed_agent_ids": ["claude-code"],
                },
            )
        ]

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    expected_status = (
        "\u6700\u8fd1\u4e00\u6b21 Orchestrator "
        "\u4efb\u52a1\u72b6\u6001\uff1a\u5df2\u5b8c\u6210"
    )
    assert expected_status in text
    assert "Create a snake game" in text
    assert "@claude-code" in text
    assert "index.html" in text


async def test_memory_store_persists_review_thread_metadata() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        task = SubTask(
            task_id="review-report",
            agent_id="codex-helper",
            title="Review report",
            instruction="Review report.md",
            depends_on=("write-report",),
            task_type="review",
            review_of=("write-report",),
            handoff_reason="Independent review before final summary",
        )
        run_id = await store.start_run(
            user_request="Review the report",
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
                text_preview="review_outcome: needs_repair",
                review_outcome="needs_repair",
            )
        )
        await store.record_task_result(run_id=run_id, task=task, result=result)
        await store.finish_run(
            run_id=run_id,
            status="done",
            final_summary=(
                "Execution summary\n"
                "- succeeded: @codex-helper - Review report\n"
                "  review outcome: needs_repair\n"
            ),
        )
        await db.commit()

    async with SessionFactory() as db:
        task_row = (
            await db.execute(
                select(OrchestratorTask).where(OrchestratorTask.run_id == run_id)
            )
        ).scalar_one()
        attempt_row = (
            await db.execute(
                select(OrchestratorTaskAttempt).where(
                    OrchestratorTaskAttempt.run_id == run_id
                )
            )
        ).scalar_one()
        planned_event = (
            await db.execute(
                select(OrchestratorRunEvent)
                .where(OrchestratorRunEvent.run_id == run_id)
                .where(OrchestratorRunEvent.event_type == "planned")
            )
        ).scalar_one()
        result_event = (
            await db.execute(
                select(OrchestratorRunEvent)
                .where(OrchestratorRunEvent.run_id == run_id)
                .where(OrchestratorRunEvent.event_type == "task_result")
            )
        ).scalar_one()

    assert task_row.task_type == "review"
    assert task_row.review_of == ["write-report"]
    assert task_row.handoff_reason == "Independent review before final summary"
    assert attempt_row.review_outcome == "needs_repair"

    task_out = OrchestratorTaskOut.model_validate(task_row)
    attempt_out = OrchestratorTaskAttemptOut.model_validate(attempt_row)
    assert task_out.task_type == "review"
    assert task_out.review_of == ["write-report"]
    assert task_out.handoff_reason == "Independent review before final summary"
    assert attempt_out.review_outcome == "needs_repair"

    planned_task = planned_event.payload["tasks"][0]
    assert planned_task["task_type"] == "review"
    assert planned_task["review_of"] == ["write-report"]
    assert planned_task["handoff_reason"] == "Independent review before final summary"
    result_attempt = result_event.payload["attempts"][0]
    assert result_attempt["review_outcome"] == "needs_repair"


async def test_agent_capability_profile_empty_without_history() -> None:
    conversation_id, _ = await _create_conversation()
    async with SessionFactory() as db:
        profile = await build_agent_capability_profile(db, conversation_id)

    assert profile == []


async def test_agent_capability_profile_aggregates_recent_agent_outcomes() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task(
            store,
            user_request="Write report",
            agent_id="codex-helper",
            task_id="write-report",
            title="Write report",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["report.md"],
        )
        await _record_memory_task(
            store,
            user_request="Create page",
            agent_id="codex-helper",
            task_id="create-page",
            title="Create page",
            final_state=TaskState.ARTIFACT_MISSING,
            missing_artifact_paths=["index.html"],
            error="Expected output was not created",
        )
        await _record_memory_task(
            store,
            user_request="Review report",
            agent_id="review-agent",
            task_id="review-report",
            title="Review report",
            final_state=TaskState.SUCCEEDED,
            task_type="review",
            review_of=("write-report",),
            review_outcome="needs_repair",
        )
        await _record_memory_task(
            store,
            user_request="Repair report",
            agent_id="codex-helper",
            task_id="repair-report",
            title="Repair report",
            final_state=TaskState.SUCCEEDED,
            task_type="repair",
            artifact_paths=["app.js"],
        )
        await _record_memory_task(
            store,
            user_request="Fix eval report",
            agent_id="codex-helper",
            task_id="eval-report",
            title="Fix eval report",
            final_state=TaskState.EVALUATION_FAILED,
            artifact_paths=["eval-repair.md"],
            evaluation_results=[
                EvaluationResult(
                    evaluator="document_quality",
                    status="failed",
                    passed=False,
                    severity="error",
                    checked_artifacts=["eval-repair.md"],
                    issues=[
                        EvaluationIssue(
                            code="placeholder_content",
                            message="Replace placeholders with complete content.",
                        )
                    ],
                )
            ],
        )
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile(db, conversation_id)

    by_agent = {item.agent_id: item for item in profile}
    codex = by_agent["codex-helper"]
    reviewer = by_agent["review-agent"]

    assert codex.task_count == 4
    assert codex.success_count == 2
    assert codex.failure_count == 2
    assert codex.artifact_missing_count == 1
    assert codex.evaluation_failed_count == 1
    assert codex.avg_attempts == 1.0
    assert codex.artifact_kinds["document"] >= 2
    assert codex.artifact_kinds["code"] == 1
    assert codex.repair_success_count == 1
    assert any("document_quality" in reason for reason in codex.recent_failure_reasons)
    assert codex.confidence in {"medium", "high"}

    assert reviewer.task_count == 1
    assert reviewer.review_outcomes == {"needs_repair": 1}


async def test_agent_capability_profile_attributes_fallback_success_to_actual_agent() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task_attempts(
            store,
            user_request="Repair fallback document",
            task_agent_id="claude-code",
            task_id="fallback-document",
            title="Fallback document",
            final_state=TaskState.SUCCEEDED,
            attempts=[
                TaskAttempt(
                    attempt_index=1,
                    agent_id="claude-code",
                    state=TaskState.EVALUATION_FAILED,
                    artifact_paths=["fallback.md"],
                    evaluation_results=[_failed_document_evaluation("fallback.md")],
                ),
                TaskAttempt(
                    attempt_index=2,
                    agent_id="opencode-helper",
                    state=TaskState.SUCCEEDED,
                    artifact_paths=["fallback.md"],
                ),
            ],
        )
        await db.commit()

    async with SessionFactory() as db:
        by_agent = {
            item.agent_id: item
            for item in await build_agent_capability_profile(db, conversation_id)
        }

    assert by_agent["claude-code"].task_count == 1
    assert by_agent["claude-code"].success_count == 0
    assert by_agent["claude-code"].failure_count == 1
    assert by_agent["claude-code"].evaluation_failed_count == 1
    assert by_agent["opencode-helper"].task_count == 1
    assert by_agent["opencode-helper"].success_count == 1
    assert by_agent["opencode-helper"].failure_count == 0


async def test_agent_capability_profile_retry_success_counts_one_task() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task_attempts(
            store,
            user_request="Retry document",
            task_agent_id="claude-code",
            task_id="retry-document",
            title="Retry document",
            final_state=TaskState.SUCCEEDED,
            attempts=[
                TaskAttempt(
                    attempt_index=1,
                    agent_id="claude-code",
                    state=TaskState.EVALUATION_FAILED,
                    artifact_paths=["retry.md"],
                    evaluation_results=[_failed_document_evaluation("retry.md")],
                ),
                TaskAttempt(
                    attempt_index=2,
                    agent_id="claude-code",
                    state=TaskState.SUCCEEDED,
                    artifact_paths=["retry.md"],
                ),
            ],
        )
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile(db, conversation_id)

    assert len(profile) == 1
    item = profile[0]
    assert item.task_count == 1
    assert item.success_count == 1
    assert item.failure_count == 0
    assert item.avg_attempts == 2.0
    assert item.evaluation_failed_count == 1
    assert item.artifact_kinds == {"document": 1}


async def test_agent_capability_profile_skips_skipped_tasks() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task(
            store,
            user_request="Skip task",
            agent_id="claude-code",
            task_id="skipped-task",
            title="Skipped task",
            final_state=TaskState.SKIPPED,
        )
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile(db, conversation_id)

    assert profile == []


async def test_agent_capability_profile_attributes_repair_success_to_fallback() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task_attempts(
            store,
            user_request="Repair with fallback",
            task_agent_id="claude-code",
            task_id="repair-fallback",
            title="Repair fallback",
            final_state=TaskState.SUCCEEDED,
            task_type="repair",
            attempts=[
                TaskAttempt(
                    attempt_index=1,
                    agent_id="claude-code",
                    state=TaskState.FAILED,
                    error="repair failed",
                ),
                TaskAttempt(
                    attempt_index=2,
                    agent_id="opencode-helper",
                    state=TaskState.SUCCEEDED,
                    artifact_paths=["repaired.md"],
                ),
            ],
        )
        await db.commit()

    async with SessionFactory() as db:
        by_agent = {
            item.agent_id: item
            for item in await build_agent_capability_profile(db, conversation_id)
        }

    assert by_agent["claude-code"].repair_success_count == 0
    assert by_agent["opencode-helper"].repair_success_count == 1


async def test_agent_capability_profile_dedupes_artifact_kind_from_attempt_and_event() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task_attempts(
            store,
            user_request="Retry same artifact kind",
            task_agent_id="codex-helper",
            task_id="same-artifact-kind",
            title="Same artifact kind",
            final_state=TaskState.SUCCEEDED,
            attempts=[
                TaskAttempt(
                    attempt_index=1,
                    agent_id="codex-helper",
                    state=TaskState.ARTIFACT_MISSING,
                    artifact_paths=["same.md"],
                    missing_artifact_paths=["same.md"],
                ),
                TaskAttempt(
                    attempt_index=2,
                    agent_id="codex-helper",
                    state=TaskState.SUCCEEDED,
                    artifact_paths=["same.md"],
                ),
            ],
        )
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile(db, conversation_id)

    assert profile[0].artifact_kinds == {"document": 1}
    assert profile[0].artifact_missing_count == 1


async def test_agent_capability_profile_supports_legacy_task_without_attempt() -> None:
    conversation_id, _ = await _create_conversation()
    run_id = uuid4()
    async with SessionFactory() as db:
        db.add(
            OrchestratorRun(
                id=run_id,
                conversation_id=conversation_id,
                status="done",
                user_request="Legacy task",
                plan_source="legacy",
                final_summary="Legacy task completed",
            )
        )
        db.add(
            OrchestratorTask(
                id=uuid4(),
                run_id=run_id,
                task_id="legacy-task",
                agent_id="legacy-agent",
                title="Legacy task",
                instruction="Legacy task",
                depends_on=[],
                priority=0,
                include_history=True,
                task_type="implementation",
                review_of=[],
                final_state="succeeded",
            )
        )
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile(db, conversation_id)

    assert len(profile) == 1
    assert profile[0].agent_id == "legacy-agent"
    assert profile[0].task_count == 1
    assert profile[0].success_count == 1
    assert profile[0].avg_attempts == 0.0


async def test_agent_capability_profile_v2_aggregates_user_conversations_only() -> None:
    user_id, conversation_a, message_a = await _create_user_conversation()
    conversation_b, message_b = await _create_conversation_for_user(user_id)
    other_user_id, other_conversation, other_message = await _create_user_conversation()
    assert other_user_id != user_id

    async with SessionFactory() as db:
        store_a = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_a,
            agent_message_id=message_a,
            user_message_id=None,
        )
        await _record_memory_task(
            store_a,
            user_request="请用中文写一个部署说明文档",
            agent_id="agent-user",
            task_id="doc-a",
            title="Write deployment doc",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["deploy.md"],
        )
        store_b = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_b,
            agent_message_id=message_b,
            user_message_id=None,
        )
        await _record_memory_task(
            store_b,
            user_request="Build frontend preview on port 8082",
            agent_id="agent-user",
            task_id="frontend-b",
            title="Build frontend",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["index.html"],
        )
        other_store = OrchestratorMemoryStore(
            db,
            conversation_id=other_conversation,
            agent_message_id=other_message,
            user_message_id=None,
        )
        await _record_memory_task(
            other_store,
            user_request="Other user task",
            agent_id="agent-other-user",
            task_id="other-task",
            title="Other user task",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["other.md"],
        )
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile_v2(
            db,
            user_id,
            conversation_id=conversation_a,
        )

    by_agent = {item.agent_id: item for item in profile.items}
    assert profile.scope == "user"
    assert profile.source_conversation_count == 2
    assert profile.runs_considered == 2
    assert set(by_agent) == {"agent-user"}
    assert by_agent["agent-user"].conversation_count == 2
    assert by_agent["agent-user"].success_count == 2
    assert by_agent["agent-user"].artifact_kinds == {"document": 1, "other": 1}
    assert profile.preferences.source_conversation_count == 2
    assert profile.preferences.language_style_hints["chinese"] == 1
    assert profile.preferences.deployment_preferences["port_8082"] == 1


async def test_agent_capability_profile_v2_decay_failures_and_low_sample() -> None:
    user_id, conversation_id, agent_message_id = await _create_user_conversation()
    old_at = datetime.now(UTC) - timedelta(days=20)
    recent_at = datetime.now(UTC) - timedelta(days=1)
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        old_run = await _record_memory_task(
            store,
            user_request="Write old backend API notes",
            agent_id="old-agent",
            task_id="old-doc",
            title="Old doc",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["old.md"],
        )
        recent_run = await _record_memory_task(
            store,
            user_request="Write recent backend API notes",
            agent_id="recent-agent",
            task_id="recent-doc",
            title="Recent doc",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["recent.md"],
        )
        bad_run = await _record_memory_task(
            store,
            user_request="Create broken frontend preview",
            agent_id="bad-agent",
            task_id="bad-doc",
            title="Bad doc",
            final_state=TaskState.ARTIFACT_MISSING,
            artifact_paths=["bad.md"],
            missing_artifact_paths=["index.html"],
            error="request timeout while creating artifact",
        )
        eval_run = await _record_memory_task(
            store,
            user_request="Evaluate broken document",
            agent_id="bad-agent",
            task_id="eval-doc",
            title="Eval doc",
            final_state=TaskState.EVALUATION_FAILED,
            artifact_paths=["eval.md"],
            evaluation_results=[_failed_document_evaluation("eval.md")],
        )
        await db.flush()
        for run_id, created_at in (
            (old_run, old_at),
            (recent_run, recent_at),
            (bad_run, recent_at),
            (eval_run, recent_at),
        ):
            run = await db.get(OrchestratorRun, run_id)
            assert run is not None
            run.created_at = created_at
            run.completed_at = created_at
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile_v2(
            db,
            user_id,
            conversation_id=conversation_id,
            half_life_days=5.0,
        )

    by_agent = {item.agent_id: item for item in profile.items}
    assert by_agent["recent-agent"].weighted_success_score > by_agent[
        "old-agent"
    ].weighted_success_score
    assert by_agent["recent-agent"].confidence == "low"
    assert "low_sample_confidence" in by_agent["recent-agent"].score_reasons
    bad = by_agent["bad-agent"]
    assert bad.timeout_count == 1
    assert bad.artifact_missing_count == 1
    assert bad.evaluation_failed_count == 1
    assert any("timeout" in reason for reason in bad.score_reasons)
    assert any("evaluation_failed" in reason for reason in bad.score_reasons)
    assert any("artifact_missing" in reason for reason in bad.score_reasons)


async def test_memory_context_includes_v2_profile_and_user_preferences() -> None:
    user_id, conversation_id, agent_message_id = await _create_user_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task(
            store,
            user_request="请用中文创建 frontend preview，部署到端口8082",
            agent_id="codex-helper",
            task_id="create-seed-v2",
            title="Create seed v2",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["index.html"],
        )
        await db.commit()

    async with SessionFactory() as db:
        memory = await build_orchestrator_memory_context(
            db,
            conversation_id,
            user_id=user_id,
            max_chars=2000,
        )

    assert memory is not None
    assert "Agent capability profile v2 from recent user Orchestrator runs" in memory.content
    assert "User preference memory from recent Orchestrator runs" in memory.content
    assert "Agent capability profile from recent Orchestrator runs" in memory.content
    assert memory.content.index(
        "Agent capability profile v2 from recent user Orchestrator runs"
    ) < memory.content.index("User preference memory from recent Orchestrator runs")
    assert memory.content.index(
        "User preference memory from recent Orchestrator runs"
    ) < memory.content.index("Agent capability profile from recent Orchestrator runs")


async def test_memory_context_sanitizes_runtime_failure_reasons() -> None:
    user_id, conversation_id, agent_message_id = await _create_user_conversation()
    raw_error = (
        "Codex CLI exited with code 1: stderr: Reading additional input from stdin... "
        "OpenAI Codex v0.137.0 -------- workdir: /workspaces/example "
        "model: gpt-5.5 provider: openai approval: never "
        "sandbox: danger-full-access System: AgentHub workspace rules"
    )
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task(
            store,
            user_request="触发一次运行时失败",
            agent_id="codex-helper",
            task_id="runtime-failure",
            title="Runtime failure",
            final_state=TaskState.FAILED,
            error=raw_error,
        )
        await db.commit()

    async with SessionFactory() as db:
        profile = await build_agent_capability_profile_v2(
            db,
            user_id,
            conversation_id=conversation_id,
        )
        memory = await build_orchestrator_memory_context(
            db,
            conversation_id,
            user_id=user_id,
            max_chars=4000,
        )

    codex_profile = next(
        item for item in profile.items if item.agent_id == "codex-helper"
    )
    assert codex_profile.recent_failure_reasons == [
        "external_runtime_error: exit_code_1"
    ]
    assert memory is not None
    assert "external_runtime_error: exit_code_1" in memory.content
    for forbidden in (
        "OpenAI Codex",
        "workdir:",
        "/workspaces/",
        "approval:",
        "sandbox:",
        "System: AgentHub workspace rules",
    ):
        assert forbidden not in memory.content


async def test_memory_context_uses_user_v2_profile_without_current_runs() -> None:
    user_id, seed_conversation_id, seed_agent_message_id = (
        await _create_user_conversation()
    )
    empty_conversation_id, _ = await _create_conversation_for_user(user_id)
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=seed_conversation_id,
            agent_message_id=seed_agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task(
            store,
            user_request="请用中文创建一份长期偏好画像文档",
            agent_id="opencode-helper",
            task_id="seed-user-v2-profile",
            title="Seed user v2 profile",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["user-profile.md"],
        )
        await db.commit()

    async with SessionFactory() as db:
        memory = await build_orchestrator_memory_context(
            db,
            empty_conversation_id,
            user_id=user_id,
            max_chars=2000,
        )

    assert memory is not None
    assert "Agent capability profile v2 from recent user Orchestrator runs" in (
        memory.content
    )
    assert "User preference memory from recent Orchestrator runs" in memory.content
    assert "@opencode-helper" in memory.content
    assert "Previous Orchestrator structured memory" not in memory.content
    assert "Agent capability profile from recent Orchestrator runs:" not in memory.content


async def test_memory_context_includes_capability_profile_and_respects_budget() -> None:
    conversation_id, agent_message_id = await _create_conversation()
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=conversation_id,
            agent_message_id=agent_message_id,
            user_message_id=None,
        )
        await _record_memory_task(
            store,
            user_request="Create capability profile seed",
            agent_id="codex-helper",
            task_id="create-seed",
            title="Create seed",
            final_state=TaskState.SUCCEEDED,
            artifact_paths=["seed.md"],
        )
        await db.commit()

    async with SessionFactory() as db:
        memory = await build_orchestrator_memory_context(
            db,
            conversation_id,
            max_chars=2000,
        )

    assert memory is not None
    assert len(memory.content) <= 2000
    assert "Agent capability profile from recent Orchestrator runs" in memory.content
    assert memory.content.index(
        "Agent capability profile from recent Orchestrator runs"
    ) < memory.content.index("Previous Orchestrator structured memory")


async def _record_memory_task(
    store: OrchestratorMemoryStore,
    *,
    user_request: str,
    agent_id: str,
    task_id: str,
    title: str,
    final_state: TaskState,
    task_type: str = "implementation",
    review_of: tuple[str, ...] = (),
    artifact_paths: list[str] | None = None,
    missing_artifact_paths: list[str] | None = None,
    review_outcome: str | None = None,
    evaluation_results: list[EvaluationResult] | None = None,
    error: str | None = None,
) -> UUID:
    return await _record_memory_task_attempts(
        store,
        user_request=user_request,
        task_agent_id=agent_id,
        task_id=task_id,
        title=title,
        final_state=final_state,
        task_type=task_type,
        review_of=review_of,
        attempts=[
            TaskAttempt(
                attempt_index=1,
                agent_id=agent_id,
                state=final_state,
                text_preview=f"{title} completed",
                artifact_paths=artifact_paths or [],
                missing_artifact_paths=missing_artifact_paths or [],
                review_outcome=review_outcome,
                evaluation_results=evaluation_results or [],
                error=error,
            )
        ],
    )


async def _record_memory_task_attempts(
    store: OrchestratorMemoryStore,
    *,
    user_request: str,
    task_agent_id: str,
    task_id: str,
    title: str,
    final_state: TaskState,
    attempts: list[TaskAttempt],
    task_type: str = "implementation",
    review_of: tuple[str, ...] = (),
) -> UUID:
    artifact_paths = [
        path
        for attempt in attempts
        for path in attempt.artifact_paths + attempt.missing_artifact_paths
    ]
    task = SubTask(
        task_id=task_id,
        agent_id=task_agent_id,
        title=title,
        instruction=title,
        task_type=task_type,
        review_of=review_of,
        expected_output="\n".join(artifact_paths) or None,
    )
    run_id = await store.start_run(
        user_request=user_request,
        plan_source="LLM planner/config",
        tasks=[task],
    )
    result = TaskResult(task_id=task.task_id, title=task.title, final_state=final_state)
    result.attempts.extend(attempts)
    await store.record_task_result(run_id=run_id, task=task, result=result)
    await store.finish_run(
        run_id=run_id,
        status="done" if final_state == TaskState.SUCCEEDED else "error",
        final_summary=f"Execution summary\n- {final_state.value}: @{task_agent_id} - {title}",
    )
    return run_id


def _failed_document_evaluation(path: str) -> EvaluationResult:
    return EvaluationResult(
        evaluator="document_quality",
        status="failed",
        passed=False,
        severity="error",
        checked_artifacts=[path],
        issues=[
            EvaluationIssue(
                code="placeholder_content",
                message="Replace placeholders with complete content.",
            )
        ],
    )
