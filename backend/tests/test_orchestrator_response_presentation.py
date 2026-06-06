"""Tests for Orchestrator final response presentation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.orchestrator._internal.execution.presentation import (
    presented_response_text,
)
from app.agents.orchestrator._internal.execution.process_block import (
    contains_forbidden_process_text,
    execution_process_block,
)
from app.agents.orchestrator.evaluation import EvaluationResult
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


class FakePolishGateway:
    def __init__(self, text: str = "", *, error: bool = False) -> None:
        self.text = text
        self.error = error
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
        yield StreamChunk(event_type="start", agent_id="polish")
        if self.error:
            yield StreamChunk(
                event_type="error",
                agent_id="polish",
                error_code="upstream_error",
                error="boom",
            )
            return
        if self.text:
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(event_type="delta", block_index=0, text_delta=self.text)
            yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id="polish")


def _context() -> tuple[list[SubTask], dict[str, TaskState], OrchestratorRunContext]:
    task = SubTask(
        task_id="task-a",
        agent_id="agent-a",
        title="Write report",
        instruction="Create report.md",
        expected_output="report.md",
    )
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        state=TaskState.SUCCEEDED,
        artifact_paths=["report.md"],
        evaluation_results=[
            EvaluationResult(
                evaluator="document_quality",
                status="passed",
                passed=True,
                checked_artifacts=["report.md"],
            )
        ],
    )
    result = TaskResult(
        task_id=task.task_id,
        title=task.title,
        final_state=TaskState.SUCCEEDED,
        attempts=[attempt],
    )
    context = OrchestratorRunContext()
    context.record(result)
    return [task], {task.task_id: TaskState.SUCCEEDED}, context


async def test_deterministic_summary_filters_internal_trace_terms() -> None:
    tasks, states, context = _context()

    text = await presented_response_text(
        {},
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\nTools: Read(report.md) result ok call_123\n",
    )

    assert "Execution summary" not in text
    assert "Tools:" not in text
    assert "result ok" not in text
    assert "call_" not in text
    assert "Write report" in text
    assert "report.md" in text
    assert "validation check(s) passed" in text


async def test_pending_tasks_make_visible_summary_partial() -> None:
    tasks, states, context = _context()
    pending = SubTask(
        task_id="task-b",
        agent_id="agent-b",
        title="Publish follow-up",
        instruction="Publish the report.",
    )

    text = await presented_response_text(
        {},
        [ChatMessage(role="user", content="Create and publish a report")],
        [*tasks, pending],
        {**states, pending.task_id: TaskState.PENDING},
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert "Done. I completed the requested work." not in text
    assert "I completed the parts that could be finished" in text
    assert "Publish follow-up" in text
    assert "was not run before orchestration stopped" in text


async def test_polish_success_uses_model_output() -> None:
    tasks, states, context = _context()
    gateway = FakePolishGateway("Done. I wrote `report.md` and validation passed.")

    text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": gateway,
            "orchestrator_response_polish_max_tokens": 321,
        },
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert text == "Done. I wrote `report.md` and validation passed.\n"
    assert gateway.calls[0]["config"]["max_tokens"] == 321
    assert "raw_summary_excerpt" not in gateway.calls[0]["messages"][0].content
    assert "Write report" in gateway.calls[0]["messages"][0].content


async def test_polish_forbidden_or_empty_output_falls_back() -> None:
    tasks, states, context = _context()
    forbidden = FakePolishGateway("Observation: Tool read result ok call_abc")
    empty = FakePolishGateway("")

    forbidden_text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": forbidden,
        },
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )
    empty_text = await presented_response_text(
        {
            "orchestrator_response_polish_enabled": True,
            "orchestrator_response_polish_gateway": empty,
        },
        [ChatMessage(role="user", content="Create a report")],
        tasks,
        states,
        context,
        "Execution summary\n- succeeded: @agent-a - Write report\n",
    )

    assert "Observation:" not in forbidden_text
    assert "call_" not in forbidden_text
    assert "Write report" in forbidden_text
    assert empty_text == forbidden_text


async def test_process_block_marks_pending_tasks_partial_and_sanitizes_terms() -> None:
    tasks, states, context = _context()
    pending = SubTask(
        task_id="task-b",
        agent_id="agent-b",
        title="Publish follow-up",
        instruction="Publish the report.",
    )

    payload = execution_process_block(
        [ChatMessage(role="user", content="Create and publish a report")],
        [*tasks, pending],
        {**states, pending.task_id: TaskState.PENDING},
        context,
    )

    assert payload["status"] == "partial"
    assert payload["steps"][2]["status"] == "skipped"
    assert "task-b" not in str(payload)
    assert not contains_forbidden_process_text(payload)
