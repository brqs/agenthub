"""Tests for OrchestratorAdapter injection-based dispatch."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.orchestrator.artifacts import (
    check_attempt_artifacts,
    extract_artifact_paths_from_text,
    finalize_artifact_candidates,
)
from app.agents.orchestrator.types import SubTask, TaskAttempt, TaskState
from app.agents.orchestrator.workspace_changes import (
    diff_workspace_snapshots,
    snapshot_workspace,
)
from app.agents.registry import get_adapter
from app.agents.types import ChatMessage, StreamChunk
from app.models.agent import Agent
from app.services.artifact_manifest import ArtifactManifestService
from app.services.workspace_workflow_runtime import WorkspaceWorkflowRuntimeService
from tests.orchestrator_fakes import (
    FakeAnswerGateway,
    FakePartialThenExceptionAdapter,
    FakePlannerGateway,
    FakeSubAdapter,
    FakeWorkspaceVerifierAdapter,
    FakeWorkspaceWriterAdapter,
    _assert_blocks_balanced,
    _collect,
    _task,
    _text_chunks,
)


class BarrierAdapter(BaseAgentAdapter):
    provider = "fake"

    def __init__(
        self,
        agent_id: str,
        started: set[str],
        all_started: asyncio.Event,
        expected_count: int,
    ) -> None:
        super().__init__(agent_id=agent_id)
        self.started = started
        self.all_started = all_started
        self.expected_count = expected_count

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ):
        _ = messages, system_prompt, config, workspace_path, tool_specs
        self.started.add(self.agent_id)
        if len(self.started) >= self.expected_count:
            self.all_started.set()
        await asyncio.wait_for(self.all_started.wait(), timeout=1)
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta",
            block_index=0,
            text_delta=f"{self.agent_id} done",
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)


class FakeMemoryWriter:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.events: list[tuple[str, str | None, str | None, dict[str, object] | None]] = []

    async def start_run(
        self,
        *,
        user_request: str,
        plan_source: str,
        tasks: list[Any],
    ) -> UUID:
        _ = user_request, plan_source, tasks
        return self.run_id

    async def record_task_planned(self, *, run_id: UUID, task: Any) -> None:
        _ = run_id, task

    async def record_task_started(
        self,
        *,
        run_id: UUID,
        task: Any,
        agent_id: str,
        attempt_index: int,
    ) -> None:
        _ = run_id, task, agent_id, attempt_index

    async def record_task_result(
        self,
        *,
        run_id: UUID,
        task: Any,
        result: Any,
    ) -> None:
        _ = run_id, task, result

    async def record_event(
        self,
        *,
        run_id: UUID,
        event_type: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        _ = run_id
        self.events.append((event_type, task_id, agent_id, payload))

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        final_summary: str,
    ) -> None:
        _ = run_id, status, final_summary

    async def cancel_active_run(self) -> None:
        pass


class FailingArtifactManifestService(ArtifactManifestService):
    def upsert_entry(self, workspace_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
        _ = workspace_root, entry
        raise RuntimeError("manifest write failed")


def test_workspace_snapshot_diff_ignores_runtime_metadata(tmp_path: Path) -> None:
    (tmp_path / ".agenthub").mkdir()
    (tmp_path / ".agenthub" / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("ignored", encoding="utf-8")
    (tmp_path / "README.md").write_text("before", encoding="utf-8")

    before = snapshot_workspace(tmp_path)
    (tmp_path / "README.md").write_text("after", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('ok')", encoding="utf-8")
    after = snapshot_workspace(tmp_path)

    assert sorted(before) == ["README.md"]
    assert diff_workspace_snapshots(before, after) == {
        "created": ["app.py"],
        "modified": ["README.md"],
        "deleted": [],
    }


def test_artifact_check_resolves_unique_basename_in_nested_workspace(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "frontend-demo"
    nested.mkdir()
    (nested / "index.html").write_text("<!doctype html>", encoding="utf-8")
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        artifact_paths=["index.html"],
    )

    check_attempt_artifacts(attempt, tmp_path)

    assert attempt.state == TaskState.SUCCEEDED
    assert attempt.artifact_paths == ["frontend-demo/index.html"]
    assert attempt.missing_artifact_paths == []


def test_artifact_check_accepts_workspace_prefixed_expected_output(
    tmp_path: Path,
) -> None:
    (tmp_path / "parallel-claude.md").write_text("ok", encoding="utf-8")
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        artifact_paths=["workspace/parallel-claude.md"],
    )

    check_attempt_artifacts(attempt, tmp_path)

    assert attempt.state == TaskState.SUCCEEDED
    assert attempt.artifact_paths == ["parallel-claude.md"]
    assert attempt.missing_artifact_paths == []


def test_artifact_extraction_accepts_absolute_workspace_tool_paths() -> None:
    assert extract_artifact_paths_from_text(
        "/workspaces/abc-123/parallel-opencode.md"
    ) == ["parallel-opencode.md"]


def test_artifact_extraction_accepts_rich_artifact_suffixes() -> None:
    assert extract_artifact_paths_from_text(
        "Created deck.pptx, brief.pdf, export.tar.gz, logo.png, data.csv"
    ) == ["deck.pptx", "brief.pdf", "export.tar.gz", "logo.png", "data.csv"]


def test_artifact_check_keeps_ambiguous_basename_missing(tmp_path: Path) -> None:
    for dirname in ("a", "b"):
        nested = tmp_path / dirname
        nested.mkdir()
        (nested / "index.html").write_text("<!doctype html>", encoding="utf-8")
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        artifact_paths=["index.html"],
    )

    check_attempt_artifacts(attempt, tmp_path)

    assert attempt.state == TaskState.ARTIFACT_MISSING
    assert attempt.missing_artifact_paths == ["index.html"]


def test_artifact_extraction_ignores_hidden_workspace_metadata() -> None:
    assert extract_artifact_paths_from_text(".agenthub/manifest.json") == []


def test_artifact_candidates_prefer_observed_outputs_over_instruction_context() -> None:
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        artifact_paths=["styles.css"],
    )
    task = SubTask(
        task_id="task-a",
        agent_id="agent-a",
        title="Create CSS",
        instruction="Read index.html for context, then create styles.css.",
    )

    finalize_artifact_candidates(attempt, task)

    assert attempt.artifact_paths == ["styles.css"]


def test_artifact_candidates_use_expected_output_as_required_contract() -> None:
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        artifact_paths=["review.md", "sitemap.xml"],
    )
    task = SubTask(
        task_id="task-a",
        agent_id="agent-a",
        title="Create review",
        instruction="Create review.md and mention sitemap.xml as a future idea.",
        expected_output="workspace 文件 review.md",
    )

    finalize_artifact_candidates(attempt, task)

    assert attempt.artifact_paths == ["review.md"]


async def test_orchestrator_emits_planning_agent_switch_subagent_and_summary() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("backend done"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("frontend done"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-b", "agent-b", "Frontend UI", "Build UI", priority=2),
                _task("task-a", "agent-a", "Backend API", "Build API", priority=1),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[0].event_type == "start"
    assert chunks[-1].event_type == "done"
    assert [chunk.event_type for chunk in chunks].count("start") == 1
    assert [chunk.event_type for chunk in chunks].count("done") == 1
    assert any(
        chunk.event_type == "delta" and "Planned 2 sub-task(s)" in (chunk.text_delta or "")
        for chunk in chunks
    )
    task_cards = [
        chunk
        for chunk in chunks
        if chunk.event_type == "block_start" and chunk.block_type == "task_card"
    ]
    assert len(task_cards) == 1
    assert task_cards[0].metadata == {
        "title": "Orchestrator 调度计划",
        "tasks": [
            {
                "id": "task-a",
                "agent_id": "agent-a",
                "title": "Backend API",
                "status": "pending",
            },
            {
                "id": "task-b",
                "agent_id": "agent-b",
                "title": "Frontend UI",
                "status": "pending",
            },
        ],
    }
    assert [
        (chunk.from_agent, chunk.to_agent, chunk.task)
        for chunk in chunks
        if chunk.event_type == "agent_switch"
    ] == [
        ("orchestrator", "agent-a", "Backend API"),
        ("orchestrator", "agent-b", "Frontend UI"),
    ]
    assert any(chunk.text_delta == "backend done" for chunk in chunks)
    assert any(chunk.text_delta == "frontend done" for chunk in chunks)
    assert any("Execution summary" in (chunk.text_delta or "") for chunk in chunks)
    assert not any(
        chunk.event_type == "delta" and (chunk.text_delta or "").startswith("@agent-")
        for chunk in chunks
    )


async def test_orchestrator_agent_review_thread_auto_reviews_artifact_task(
    tmp_path: Path,
) -> None:
    implementation = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "# Report\n\nReady for review.",
    )
    reviewer = FakeSubAdapter(
        "agent-b",
        _text_chunks(
            "review_outcome: passed\n"
            "Artifact report.md exists and the handoff is confirmed."
        ),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Create report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"agent-a": implementation, "agent-b": reviewer},
            "orchestrator_agent_review_enabled": True,
        },
    )

    switches = [
        (chunk.to_agent, chunk.task)
        for chunk in chunks
        if chunk.event_type == "agent_switch"
    ]
    assert switches == [("agent-a", "Write report"), ("agent-b", "Review Write report")]
    reviewer_context = "\n".join(message.content for message in reviewer.received_messages)
    assert "Previous sub-agent results" in reviewer_context
    assert "task-a @agent-a succeeded" in reviewer_context
    assert "Artifacts: report.md" in reviewer_context
    assert "Agent-to-Agent Review Thread" in reviewer.received_messages[-1].content
    assert "review_outcome: passed" in reviewer.received_messages[-1].content
    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert "@agent-b [review] - Review Write report" in summary
    assert "review_of: task-a" in summary
    assert "review outcome: passed" in summary


async def test_orchestrator_rich_artifact_updates_manifest(
    tmp_path: Path,
) -> None:
    conversation_id = uuid4()
    writer = FakeMemoryWriter()
    implementation = FakeWorkspaceWriterAdapter(
        "codex-helper",
        _text_chunks("Created report.md"),
        "report.md",
        "# Report\n\nThis section contains concrete validation evidence and next steps.",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "conversation_id": conversation_id,
            "orchestrator_memory_writer": writer,
            "tasks": [
                _task(
                    "task-report",
                    "codex-helper",
                    "Write report",
                    "Create report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"codex-helper": implementation},
        },
    )

    file_start = next(
        chunk
        for chunk in chunks
        if chunk.event_type == "block_start" and chunk.block_type == "file"
    )
    assert file_start.agent_id == "codex-helper"
    assert file_start.metadata
    assert file_start.metadata["path"] == "report.md"
    assert file_start.metadata["artifact_kind"] == "document"

    entries = ArtifactManifestService().list_entries(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["path"] == "report.md"
    assert entry["artifact_kind"] == "document"
    assert entry["agent_id"] == "codex-helper"
    assert entry["task_id"] == "task-report"
    assert entry["run_id"] == str(writer.run_id)
    assert entry["evaluation_status"] == "passed"
    assert any(result["evaluator"] == "document_quality" for result in entry["evaluation_results"])


async def test_orchestrator_manifest_failure_keeps_stream_done(
    tmp_path: Path,
) -> None:
    writer = FakeMemoryWriter()
    implementation = FakeWorkspaceWriterAdapter(
        "codex-helper",
        _text_chunks("Created report.md"),
        "report.md",
        "# Report\n\nThis section contains concrete validation evidence and next steps.",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "conversation_id": uuid4(),
            "orchestrator_memory_writer": writer,
            "orchestrator_artifact_manifest_service": FailingArtifactManifestService(),
            "tasks": [
                _task(
                    "task-report",
                    "codex-helper",
                    "Write report",
                    "Create report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"codex-helper": implementation},
        },
    )

    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "block_start" and chunk.block_type == "file"
        for chunk in chunks
    )
    assert any(
        event_type == "artifact_manifest_update_failed"
        for event_type, _task_id, _agent_id, _payload in writer.events
    )


async def test_orchestrator_agent_review_thread_schedules_repair_on_failed_review(
    tmp_path: Path,
) -> None:
    implementation = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "# Report\n\nThis report includes current findings, evidence, and next steps.",
    )
    reviewer = FakeSubAdapter(
        "agent-b",
        _text_chunks(
            "review_outcome: needs_repair\n"
            "Artifact report.md is missing the validation section."
        ),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Create report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"agent-a": implementation, "agent-b": reviewer},
            "orchestrator_agent_review_enabled": True,
        },
    )

    switches = [
        (chunk.to_agent, chunk.task)
        for chunk in chunks
        if chunk.event_type == "agent_switch"
    ]
    assert switches == [
        ("agent-a", "Write report"),
        ("agent-b", "Review Write report"),
        ("agent-a", "Repair Write report after review"),
    ]
    assert "Agent-to-Agent Repair Thread" in implementation.received_messages[-1].content
    assert "review_outcome: needs_repair" in implementation.received_messages[-1].content
    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert "review outcome: needs_repair" in summary
    assert "- succeeded: @agent-a - Repair Write report after review" in summary
    assert "handoff: Repair requested by @agent-b review (needs_repair)" in summary


async def test_orchestrator_parallel_review_thread_schedules_one_repair_task(
    tmp_path: Path,
) -> None:
    implementation = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "# Draft\n\nNeeds one more section.",
    )
    reviewer = FakeSubAdapter(
        "agent-b",
        _text_chunks(
            "review_outcome: needs_repair\n"
            "Artifact report.md is missing the validation section."
        ),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Create report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"agent-a": implementation, "agent-b": reviewer},
            "orchestrator_agent_review_enabled": True,
            "orchestrator_parallel_enabled": True,
        },
    )

    switches = [
        (chunk.to_agent, chunk.task)
        for chunk in chunks
        if chunk.event_type == "agent_switch"
    ]
    assert switches.count(("agent-a", "Repair Write report after review")) == 1
    assert switches == [
        ("agent-a", "Write report"),
        ("agent-b", "Review Write report"),
        ("agent-a", "Repair Write report after review"),
    ]
    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert "review outcome: needs_repair" in summary
    assert "- succeeded: @agent-a - Repair Write report after review" in summary
    assert "handoff: Repair requested by @agent-b review (needs_repair)" in summary


async def test_review_thread_parses_fenced_outcome_without_artifact_evaluation(
    tmp_path: Path,
) -> None:
    implementation = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "# Report\n\nThis report includes current findings, evidence, and next steps.",
    )
    reviewer = FakeSubAdapter(
        "agent-b",
        _text_chunks(
            "I reviewed report.md.\n\n"
            "```\n"
            "review_outcome: needs_repair\n"
            "```\n\n"
            "report.md is still placeholder content and needs repair."
        ),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Create report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"agent-a": implementation, "agent-b": reviewer},
            "orchestrator_agent_review_enabled": True,
            "orchestrator_parallel_enabled": True,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)

    assert "- succeeded: @agent-b - Review Write report" in summary
    assert "review outcome: needs_repair" in summary
    assert "Repair Write report after review" in summary
    assert "evaluation_failed: @agent-b - Review Write report" not in summary


async def test_orchestrator_hides_subagent_text_by_default() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("large sub-agent output"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = [
        chunk
        async for chunk in orchestrator.stream(
            messages=[ChatMessage(role="user", content="Build a todo app")],
            config={
                "tasks": [_task("task-a", "agent-a", "Backend API", "Build API")],
                "sub_adapters": {"agent-a": adapter_a},
            },
        )
    ]

    assert chunks[-1].event_type == "done"
    assert any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert not any(chunk.text_delta == "large sub-agent output" for chunk in chunks)
    assert any("Execution summary" in (chunk.text_delta or "") for chunk in chunks)


async def test_orchestrator_parallel_executes_independent_tasks_concurrently() -> None:
    started: set[str] = set()
    all_started = asyncio.Event()
    adapter_a = BarrierAdapter("agent-a", started, all_started, expected_count=2)
    adapter_b = BarrierAdapter("agent-b", started, all_started, expected_count=2)
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "orchestrator_parallel_enabled": True,
            "tasks": [
                _task("task-a", "agent-a", "Task A", "Do A", priority=1),
                _task("task-b", "agent-b", "Task B", "Do B", priority=1),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert started == {"agent-a", "agent-b"}
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert any(chunk.text_delta == "agent-a done" for chunk in chunks)
    assert any(chunk.text_delta == "agent-b done" for chunk in chunks)
    _assert_blocks_balanced(chunks)


async def test_orchestrator_parallel_takes_precedence_over_react_for_multi_task() -> None:
    started: set[str] = set()
    all_started = asyncio.Event()
    adapter_a = BarrierAdapter("agent-a", started, all_started, expected_count=2)
    adapter_b = BarrierAdapter("agent-b", started, all_started, expected_count=2)
    react_gateway = FakePlannerGateway([])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "orchestrator_parallel_enabled": True,
            "tasks": [
                _task("task-a", "agent-a", "Task A", "Do A", priority=1),
                _task("task-b", "agent-b", "Task B", "Do B", priority=1),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert started == {"agent-a", "agent-b"}
    assert react_gateway.calls == []
    assert chunks[-1].event_type == "done"


async def test_orchestrator_parallel_skips_failed_dependency() -> None:
    failing = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="boom",
                error="failed",
            ),
        ],
    )
    dependent = FakeSubAdapter("agent-b", _text_chunks("should not run"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "orchestrator_parallel_enabled": True,
            "tasks": [
                _task("task-a", "agent-a", "Task A", "Do A", priority=1),
                _task(
                    "task-b",
                    "agent-b",
                    "Task B",
                    "Do B",
                    priority=2,
                    depends_on=["task-a"],
                ),
            ],
            "sub_adapters": {"agent-a": failing, "agent-b": dependent},
        },
    )

    assert not dependent.received_messages
    summary = "\n".join(chunk.text_delta or "" for chunk in chunks)
    assert "failed: @agent-a - Task A" in summary
    assert "skipped: @agent-b - Task B" in summary


async def test_orchestrator_records_workspace_conflicts_in_summary(
    tmp_path: Path,
) -> None:
    writer_a = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("a wrote shared"),
        write_path="shared.txt",
        content="from a",
    )
    writer_b = FakeWorkspaceWriterAdapter(
        "agent-b",
        _text_chunks("b wrote shared"),
        write_path="shared.txt",
        content="from b",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Task A", "Write shared"),
                _task("task-b", "agent-b", "Task B", "Write shared"),
            ],
            "sub_adapters": {"agent-a": writer_a, "agent-b": writer_b},
        },
    )

    summary = "\n".join(chunk.text_delta or "" for chunk in chunks)
    assert "conflicts: shared.txt" in summary
    assert "Workspace conflicts:" in summary
    assert "@agent-a/task-a" in summary
    assert "@agent-b/task-b" in summary


async def test_orchestrator_remaps_block_indices_without_collisions() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a", block_index=0))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b", block_index=0))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    block_starts = [
        chunk.block_index for chunk in chunks if chunk.event_type == "block_start"
    ]
    assert block_starts == list(range(len(block_starts)))

    started = set(block_starts)
    for chunk in chunks:
        if chunk.event_type in {"delta", "block_end"} and chunk.block_index is not None:
            assert chunk.block_index in started

    a_delta = next(chunk for chunk in chunks if chunk.text_delta == "from a")
    b_delta = next(chunk for chunk in chunks if chunk.text_delta == "from b")
    assert a_delta.block_index != b_delta.block_index
    _assert_blocks_balanced(chunks)


async def test_orchestrator_preserves_subagent_metadata_and_delta_fields() -> None:
    sub_chunks = [
        StreamChunk(event_type="start", agent_id="agent-a"),
        StreamChunk(
            event_type="block_start",
            block_index=3,
            block_type="code",
            metadata={"language": "python", "filename": "app.py"},
        ),
        StreamChunk(event_type="delta", block_index=3, code_delta="print('ok')\n"),
        StreamChunk(event_type="block_end", block_index=3),
        StreamChunk(event_type="block_start", block_index=7, block_type="text"),
        StreamChunk(event_type="delta", block_index=7, text_delta="notes"),
        StreamChunk(event_type="block_end", block_index=7),
        StreamChunk(event_type="done", agent_id="agent-a", total_blocks=2),
    ]
    adapter_a = FakeSubAdapter("agent-a", sub_chunks)
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Code", "Write code")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    code_start = next(chunk for chunk in chunks if chunk.block_type == "code")
    code_delta = next(chunk for chunk in chunks if chunk.code_delta is not None)
    text_delta = next(chunk for chunk in chunks if chunk.text_delta == "notes")

    assert code_start.metadata == {"language": "python", "filename": "app.py"}
    assert code_start.agent_id == "agent-a"
    assert code_delta.agent_id == "agent-a"
    assert text_delta.agent_id == "agent-a"
    assert code_delta.code_delta == "print('ok')\n"
    assert code_delta.block_index == code_start.block_index
    assert text_delta.block_index != code_start.block_index


async def test_orchestrator_attribution_marks_subagent_tool_failure_and_summary() -> None:
    sub_chunks = [
        StreamChunk(event_type="start", agent_id="agent-a"),
        StreamChunk(
            event_type="tool_call",
            call_id="c-1",
            tool_name="write_file",
            tool_arguments={"path": "app.py"},
        ),
        StreamChunk(
            event_type="tool_result",
            call_id="c-1",
            tool_status="ok",
            tool_output="wrote app.py",
        ),
        StreamChunk(event_type="block_start", block_index=0, block_type="text"),
        StreamChunk(event_type="delta", block_index=0, text_delta="agent output"),
        StreamChunk(event_type="block_end", block_index=0),
        StreamChunk(
            event_type="error",
            agent_id="agent-a",
            error_code="runtime_error",
            error="boom",
        ),
    ]
    adapter_a = FakeSubAdapter("agent-a", sub_chunks)
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Work", "Do work")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    output_delta = next(chunk for chunk in chunks if chunk.text_delta == "agent output")
    failure_delta = next(
        chunk for chunk in chunks if chunk.text_delta == "failed: boom\n"
    )
    summary_delta = next(
        chunk for chunk in chunks if "Execution summary" in (chunk.text_delta or "")
    )

    assert tool_call.call_id == "task-a.c-1"
    assert tool_call.agent_id == "agent-a"
    assert tool_result.agent_id == "agent-a"
    assert output_delta.agent_id == "agent-a"
    assert failure_delta.agent_id == "agent-a"
    assert summary_delta.agent_id == "orchestrator"


async def test_orchestrator_does_not_require_database() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("factory result"))
    factory_calls: list[str] = []

    async def adapter_factory(agent_id: str) -> BaseAgentAdapter:
        factory_calls.append(agent_id)
        return adapter_a

    messages = [ChatMessage(role="user", content="Initial request")]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Injected task")],
            "adapter_factory": adapter_factory,
        },
    )

    assert chunks[-1].event_type == "done"
    assert factory_calls == ["agent-a"]
    assert adapter_a.received_messages == [
        ChatMessage(role="user", content="Initial request"),
        ChatMessage(role="user", content="Injected task"),
    ]
    assert adapter_a.received_system_prompt is None
    assert adapter_a.received_config is not None
    assert adapter_a.received_config["runtime_context"]["agent_id"] == "agent-a"
    assert adapter_a.received_config["runtime_context"]["orchestrator_task_id"] == "task-a"


async def test_orchestrator_passes_group_memory_to_sub_agent() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("used group memory"))
    messages = [
        ChatMessage(
            role="system",
            content=(
                "This is a group conversation. Assistant messages may come from "
                "multiple agents."
            ),
        ),
        ChatMessage(
            role="system",
            content="Earlier compressed conversation memory:\nAgentHub uses FastAPI.",
        ),
        ChatMessage(
            role="assistant",
            content="[Agent: claude-code]\nI created the backend API.",
        ),
        ChatMessage(role="user", content="@orchestrator continue the implementation"),
    ]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "tasks": [_task("task-a", "agent-a", "Continue", "Continue the work")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert chunks[-1].event_type == "done"
    joined = "\n".join(message.content for message in adapter_a.received_messages)
    assert "group conversation" in joined
    assert "Earlier compressed conversation memory" in joined
    assert "[Agent: claude-code]" in joined
    assert adapter_a.received_messages[-1].content == "Continue the work"


async def test_orchestrator_derives_tasks_from_managed_agents() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("analysis done"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("implementation done"))
    messages = [ChatMessage(role="user", content="Build a calendar app")]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "managed_agent_ids": ["orchestrator", "agent-a", "agent-b"],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert adapter_a.received_messages[-1].content.startswith("Analyze the user's request")
    assert "Build a calendar app" in adapter_b.received_messages[-1].content


async def test_orchestrator_derives_direct_tasks_for_named_agents() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("claude response"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("opencode response"))
    codex = FakeSubAdapter("codex-helper", _text_chunks("codex response"))
    planner = FakePlannerGateway([])
    messages = [
        ChatMessage(
            role="user",
            content=(
                '@orchestrator send claude code, opencode, and codex the same message '
                '"hello, what model are you?" and return their outputs'
            ),
        )
    ]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": [
                "claude-code",
                "codex-helper",
                "opencode-helper",
            ],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code", "opencode-helper", "codex-helper"]
    assert planner.calls == []
    assert all(
        chunk.event_type != "delta" or "Analyze request" not in (chunk.text_delta or "")
        for chunk in chunks
    )

    assert len(claude.received_messages) == 1
    assert len(opencode.received_messages) == 2
    assert len(codex.received_messages) == 2

    for adapter in (claude, opencode, codex):
        instruction = adapter.received_messages[-1].content
        assert "Message:\nhello, what model are you?" in instruction
        assert "@orchestrator" not in instruction
        assert "Do not contact, invoke, or simulate other agents" in instruction


async def test_orchestrator_answers_simple_greeting_without_planning() -> None:
    planner = FakePlannerGateway([])
    answer = FakeAnswerGateway(_text_chunks("你好，我是 AgentHub Orchestrator。"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 你好")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "managed_agent_ids": ["claude-code", "opencode-helper"],
            "sub_adapters": {
                "claude-code": FakeSubAdapter("claude-code", _text_chunks("unused")),
                "opencode-helper": FakeSubAdapter(
                    "opencode-helper", _text_chunks("unused")
                ),
            },
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "AgentHub Orchestrator" in text
    assert "Planned" not in text
    assert [chunk for chunk in chunks if chunk.event_type == "agent_switch"] == []
    assert planner.calls == []
    assert len(answer.calls) == 1


async def test_orchestrator_uses_planner_for_chinese_generation_request() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("created html"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "create-web-page",
                            "claude-code",
                            "Create campus page",
                            "Create a USTC campus web page.",
                            expected_output="index.html",
                        )
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    answer = FakeAnswerGateway(_text_chunks("should not answer directly"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator "
                    "\u8bf7\u4f60\u5e2e\u6211\u751f\u6210\u4e00\u4e2a\u7f51\u9875"
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "managed_agent_ids": ["claude-code"],
            "sub_adapters": {"claude-code": claude},
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(planner.calls) == 1
    assert answer.calls == []
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code"]


async def test_orchestrator_uses_planner_for_named_agent_file_tasks() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("created claude file"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("created opencode file"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "write-claude",
                            "claude-code",
                            "Write Claude file",
                            "Create parallel-claude.md.",
                            priority=1,
                            expected_output="parallel-claude.md",
                        ),
                        _task(
                            "write-opencode",
                            "opencode-helper",
                            "Write OpenCode file",
                            "Create parallel-opencode.md.",
                            priority=1,
                            expected_output="parallel-opencode.md",
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 让 claude-code 生成 parallel-claude.md，"
                    "让 opencode-helper 生成 parallel-opencode.md。"
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "opencode-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(planner.calls) == 1
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code", "opencode-helper"]


async def test_orchestrator_derives_workspace_conflict_plan_without_llm(
    tmp_path: Path,
) -> None:
    claude = FakeWorkspaceWriterAdapter(
        "claude-code",
        _text_chunks("wrote design"),
        "shared-conflict.md",
        "设计视角",
    )
    opencode = FakeWorkspaceWriterAdapter(
        "opencode-helper",
        _text_chunks("wrote implementation"),
        "shared-conflict.md",
        "实现视角",
    )
    planner = FakePlannerGateway([])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 请测试 workspace 冲突处理：先创建 "
                    "shared-conflict.md，然后安排 claude-code 和 opencode-helper "
                    "在同一个 run 内分别修改同一文件。"
                ),
            )
        ],
        workspace_path=tmp_path,
        config={
            "planner_gateway": planner,
            "orchestrator_parallel_enabled": True,
            "managed_agent_ids": ["claude-code", "opencode-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "opencode-helper": opencode,
            },
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert (tmp_path / "shared-conflict.md").exists()
    assert "Workspace conflicts" in text
    assert "shared-conflict.md" in text


async def test_orchestrator_smoke_flows_create_then_verify_html(
    tmp_path: Path,
) -> None:
    html_path = "orchestrator-flow-smoke.html"
    html_content = """<!doctype html>
<html>
<head><title>Orchestrator Flow Smoke Test</title></head>
<body>
  <h1>Orchestrator Flow Smoke Test</h1>
  <input id="smoke-input" />
  <button id="smoke-button">Show</button>
  <p id="smoke-output"></p>
  <script>
    document.getElementById("smoke-button").addEventListener("click", () => {
      document.getElementById("smoke-output").textContent =
        document.getElementById("smoke-input").value;
    });
  </script>
</body>
</html>
"""
    creator = FakeWorkspaceWriterAdapter(
        "codex-helper",
        [
            StreamChunk(event_type="start", agent_id="codex-helper"),
            StreamChunk(
                event_type="tool_call",
                call_id="write-1",
                tool_name="write_file",
                tool_arguments={"path": html_path, "content": html_content},
            ),
            StreamChunk(
                event_type="tool_result",
                call_id="write-1",
                tool_status="ok",
                tool_output=f"wrote {html_path}",
            ),
            *_text_chunks(f"Created {html_path}")[1:],
        ],
        write_path=html_path,
        content=html_content,
    )
    verifier = FakeWorkspaceVerifierAdapter("opencode-helper", html_path)
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "create-html",
                            "codex-helper",
                            "Create smoke HTML",
                            f"Create {html_path} with title, input, button, and display logic.",
                            priority=1,
                            expected_output=html_path,
                        ),
                        _task(
                            "verify-html",
                            "opencode-helper",
                            "Verify smoke HTML",
                            (
                                f"Verify {html_path} contains the title, input, button, "
                                "and click display behavior. Do not regenerate the file."
                            ),
                            priority=2,
                            depends_on=["create-html"],
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 请编排当前群聊里的 agent 协作完成一个极简 HTML "
                    f"文件 `{html_path}`。第一个子任务只负责创建 HTML 文件，"
                    "第二个子任务必须基于第一个子任务的结果进行检查。"
                ),
            )
        ],
        workspace_path=tmp_path,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "codex-helper", "opencode-helper"],
            "available_agents": [
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                },
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "cli", "files"],
                },
            ],
            "sub_adapters": {
                "codex-helper": creator,
                "opencode-helper": verifier,
            },
        },
    )

    persisted_html = (tmp_path / html_path).read_text(encoding="utf-8")
    planning_text = "".join(chunk.text_delta or "" for chunk in chunks)
    planner_prompt = planner.calls[0]["messages"][0].content
    verifier_system_messages = [
        message for message in verifier.received_messages if message.role == "system"
    ]
    summary = planning_text.split("Execution summary", 1)[1]

    assert chunks[-1].event_type == "done"
    assert "Planned 2 sub-task(s) via LLM planner/config" in planning_text
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["codex-helper", "opencode-helper"]
    assert "web-designer" not in planner_prompt
    assert "Previous sub-agent results" in verifier_system_messages[0].content
    assert "create-html @codex-helper succeeded" in verifier_system_messages[0].content
    assert html_path in verifier_system_messages[0].content
    assert "Created orchestrator-flow-smoke.html" in verifier_system_messages[0].content
    assert "- succeeded: @codex-helper - Create smoke HTML" in summary
    assert "- succeeded: @opencode-helper - Verify smoke HTML" in summary
    assert f"artifacts: {html_path}" in summary
    assert "Checked orchestrator-flow-smoke.html" in planning_text
    assert "title=True" in planning_text
    assert "input=True" in planning_text
    assert "button=True" in planning_text
    assert "display=True" in planning_text
    assert "Orchestrator Flow Smoke Test" in persisted_html
    assert "<input" in persisted_html
    assert "<button" in persisted_html
    assert "textContent" in persisted_html
    assert verifier.verified_content == persisted_html


async def test_orchestrator_forwards_tool_events_with_remapped_call_ids() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "hello.html"},
            ),
            StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="ok",
                tool_output="wrote hello.html",
            ),
            StreamChunk(event_type="done", agent_id="agent-a"),
        ],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Write HTML", "Write hello.html")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert tool_call.call_id == "task-a.c-1"
    assert tool_result.call_id == "task-a.c-1"
    assert tool_call.tool_name == "write_file"
    assert tool_result.tool_status == "ok"


async def test_orchestrator_injects_dependency_result_context() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Created snake.html"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("Reviewed result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Create", "Create snake.html"),
                _task(
                    "task-b",
                    "agent-b",
                    "Review",
                    "Review the prior artifact",
                    depends_on=["task-a"],
                ),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    system_messages = [
        message for message in adapter_b.received_messages if message.role == "system"
    ]
    assert len(system_messages) == 1
    assert "Previous sub-agent results" in system_messages[0].content
    assert "task-a @agent-a succeeded" in system_messages[0].content
    assert "Created snake.html" in system_messages[0].content


async def test_orchestrator_include_history_false_still_injects_dependency_context() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Analysis complete"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("Second result"))
    user_message = ChatMessage(role="user", content="Original user request")
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[user_message],
        config={
            "tasks": [
                _task("task-a", "agent-a", "Analyze", "Analyze request"),
                _task(
                    "task-b",
                    "agent-b",
                    "Direct",
                    "Use dependency only",
                    depends_on=["task-a"],
                    include_history=False,
                ),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert user_message not in adapter_b.received_messages
    assert adapter_b.received_messages[0].role == "system"
    assert "Analysis complete" in adapter_b.received_messages[0].content
    assert adapter_b.received_messages[-1].content == "Use dependency only"


async def test_orchestrator_marks_missing_expected_artifact(tmp_path: Path) -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Created snake.html"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create HTML",
                    "Create snake.html",
                    expected_output="snake.html",
                )
            ],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- artifact_missing: @agent-a - Create HTML" in summary
    assert "missing: snake.html" in summary


async def test_orchestrator_does_not_treat_future_text_mentions_as_artifacts(
    tmp_path: Path,
) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="tool_call",
                call_id="write-1",
                tool_name="write_file",
                tool_arguments={"path": "TASK_BREAKDOWN.md"},
            ),
            StreamChunk(
                event_type="tool_result",
                call_id="write-1",
                tool_status="ok",
                tool_output="wrote TASK_BREAKDOWN.md",
            ),
            *_text_chunks("Next steps will create index.html, styles.css, and app.js")[1:],
        ],
        write_path="TASK_BREAKDOWN.md",
        content="# plan",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write plan",
                    "Write TASK_BREAKDOWN.md",
                    expected_output="TASK_BREAKDOWN.md",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- succeeded: @agent-a - Write plan" in summary
    assert "missing:" not in summary


async def test_orchestrator_artifact_missing_triggers_per_task_fallback(
    tmp_path: Path,
) -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Created snake.html"))
    adapter_b = FakeWorkspaceWriterAdapter(
        "agent-b",
        [
            StreamChunk(event_type="start", agent_id="agent-b"),
            StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "snake.html"},
            ),
            StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="ok",
                tool_output="wrote snake.html",
            ),
            *_text_chunks("Fallback created snake.html")[1:],
        ],
        write_path="snake.html",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create HTML",
                    "Create snake.html",
                    expected_output="snake.html",
                )
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["agent-b"],
            "max_task_attempts": 2,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    assert (tmp_path / "snake.html").exists()
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert tool_call.call_id == "task-a.attempt-2.c-1"
    assert "- succeeded: @agent-b - Create HTML" in summary
    assert "attempt 1 @agent-a: artifact_missing" in summary
    assert "artifacts: snake.html" in summary


async def test_orchestrator_evaluation_repairs_empty_document(
    tmp_path: Path,
) -> None:
    adapter_a = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "",
    )
    adapter_b = FakeWorkspaceWriterAdapter(
        "agent-b",
        _text_chunks("Completed report.md"),
        "report.md",
        "# Report\n\nThis document now contains complete task-specific content.",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Write report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["agent-b"],
            "max_task_attempts": 2,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert "- succeeded: @agent-b - Write report" in summary
    assert "attempt 1 @agent-a: evaluation_failed" in summary
    assert "document_quality/empty_document" in summary
    assert "Previous attempt failure" in adapter_b.received_messages[-2].content
    assert "Revise the workspace artifacts" in adapter_b.received_messages[-2].content


async def test_orchestrator_appends_file_block_for_rich_artifact(
    tmp_path: Path,
) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "# Report\n\nThis section contains useful task-specific artifact details.",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "conversation_id": uuid4(),
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Write report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    file_starts = [
        chunk
        for chunk in chunks
        if chunk.event_type == "block_start" and chunk.block_type == "file"
    ]
    assert file_starts
    assert file_starts[0].agent_id == "agent-a"
    assert file_starts[0].metadata
    assert file_starts[0].metadata["artifact_kind"] == "document"
    assert file_starts[0].metadata["path"] == "report.md"
    assert file_starts[0].metadata["preview_text"].startswith("# Report")


async def test_orchestrator_evaluation_fails_invalid_python_without_fatal(
    tmp_path: Path,
) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created app.py"),
        "app.py",
        "def broken(:\n",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write Python",
                    "Write app.py",
                    expected_output="app.py",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- evaluation_failed: @agent-a - Write Python" in summary
    assert "code_static_quality/parse_error" in summary
    assert "Fix the syntax in app.py" in summary


async def test_orchestrator_evaluation_can_be_disabled(tmp_path: Path) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created app.py"),
        "app.py",
        "def broken(:\n",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write Python",
                    "Write app.py",
                    expected_output="app.py",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
            "orchestrator_evaluation_enabled": False,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- succeeded: @agent-a - Write Python" in summary
    assert "evaluation_failed" not in summary


async def test_orchestrator_evaluation_skips_over_read_budget(tmp_path: Path) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "TODO placeholder unfinished content that would fail if read",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Write report.md",
                    expected_output="report.md",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
            "orchestrator_evaluation_read_max_bytes": 10,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- succeeded: @agent-a - Write report" in summary
    assert "document_quality" not in summary


async def test_orchestrator_evaluation_ignores_sensitive_expected_output(
    tmp_path: Path,
) -> None:
    (tmp_path / "secrets").mkdir()
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created sensitive output"),
        "secrets/report.md",
        "",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write sensitive report",
                    "Write secrets/report.md",
                    expected_output="secrets/report.md",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- succeeded: @agent-a - Write sensitive report" in summary
    assert "evaluation_failed" not in summary


async def test_orchestrator_test_runner_allowlist_reports_failure(
    tmp_path: Path,
) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created app.py"),
        "app.py",
        "def broken(:\n",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Run tests",
                    "Create app.py and run tests",
                    expected_output="app.py",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
            "orchestrator_test_runner_enabled": True,
            "orchestrator_test_command_allowlist": ["python_compile_artifacts"],
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- evaluation_failed: @agent-a - Run tests" in summary
    assert "test_report_quality/test_runner_failed" in summary
    assert "py_compile" in summary


async def test_orchestrator_workflow_validation_rejects_dangling_edge(
    tmp_path: Path,
) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created workflow.json"),
        "workflow.json",
        (
            '{"version":"1","name":"Demo","nodes":[{"id":"start","type":"start"}],'
            '"edges":[{"source":"start","target":"missing"}]}'
        ),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create workflow",
                    "Create workflow.json",
                    expected_output="workflow.json",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- evaluation_failed: @agent-a - Create workflow" in summary
    assert "workflow_validation/workflow_dangling_edge_target" in summary


async def test_orchestrator_workflow_validation_triggers_dry_run(
    tmp_path: Path,
) -> None:
    class FakeWorkflowRuntime(WorkspaceWorkflowRuntimeService):
        def __init__(self) -> None:
            self.paths: list[str] = []

        async def dry_run(  # type: ignore[override]
            self,
            db: Any,
            conversation_id: Any,
            *,
            path: str,
            inputs: dict[str, Any] | None = None,
        ) -> Any:
            _ = db, conversation_id, inputs
            self.paths.append(path)
            return SimpleNamespace(
                id=uuid4(),
                status="passed",
                runtime_status="ready",
                dry_run_status="passed",
                health_status="passed",
                node_results=[{"node_id": "start", "status": "passed"}],
            )

    workflow_runtime = FakeWorkflowRuntime()
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created workflow.json"),
        "workflow.json",
        (
            '{"version":"1","name":"Demo","nodes":[{"id":"start","type":"trigger"}],'
            '"edges":[]}'
        ),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "conversation_id": uuid4(),
            "orchestrator_db_session": object(),
            "orchestrator_workflow_runtime_service": workflow_runtime,
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create workflow",
                    "Create workflow.json",
                    expected_output="workflow.json",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert workflow_runtime.paths == ["workflow.json"]
    assert chunks[-1].event_type == "done"
    assert "- succeeded: @agent-a - Create workflow" in summary
    assert "workflow dry-run: workflow.json passed" in summary


async def test_orchestrator_ppt_validation_rejects_empty_slides(
    tmp_path: Path,
) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created ppt_outline.json"),
        "ppt_outline.json",
        '{"title":"Quarterly Review","slides":[]}',
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create PPT",
                    "Create ppt_outline.json",
                    expected_output="ppt_outline.json",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- evaluation_failed: @agent-a - Create PPT" in summary
    assert "ppt_validation/ppt_no_slides" in summary


async def test_orchestrator_pptx_validation_rejects_corrupt_binary(
    tmp_path: Path,
) -> None:
    adapter = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created deck.pptx"),
        "deck.pptx",
        "not a real pptx but binary parsing is skipped",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create PPT",
                    "Create deck.pptx",
                    expected_output="deck.pptx",
                )
            ],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- evaluation_failed: @agent-a - Create PPT" in summary
    assert "ppt_validation/pptx_parse_error" in summary


async def test_orchestrator_parallel_evaluation_failure_skips_dependency(
    tmp_path: Path,
) -> None:
    adapter_a = FakeWorkspaceWriterAdapter(
        "agent-a",
        _text_chunks("Created report.md"),
        "report.md",
        "",
    )
    adapter_b = FakeWorkspaceWriterAdapter(
        "agent-b",
        _text_chunks("Created review.md"),
        "review.md",
        "# Review",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Write report",
                    "Write report.md",
                    expected_output="report.md",
                ),
                _task(
                    "task-b",
                    "agent-b",
                    "Review report",
                    "Use report.md to write review.md",
                    depends_on=["task-a"],
                    expected_output="review.md",
                ),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "orchestrator_parallel_enabled": True,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- evaluation_failed: @agent-a - Write report" in summary
    assert "- skipped: @agent-b - Review report" in summary
    assert not (tmp_path / "review.md").exists()


async def test_orchestrator_subagent_error_triggers_per_task_fallback() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="runtime_idle_timeout",
                error="idle timeout",
            ),
        ],
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("Recovered result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Work", "Do work")],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["agent-b"],
            "max_task_attempts": 2,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert "Previous attempt failure" in adapter_b.received_messages[-2].content
    assert "idle timeout" in adapter_b.received_messages[-2].content
    assert "- succeeded: @agent-b - Work" in summary
    assert "attempt 1 @agent-a: failed - idle timeout" in summary


async def test_orchestrator_fallbacks_are_limited_to_current_agents() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="runtime_error",
                error="boom",
            )
        ],
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("Recovered result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Work", "Do work")],
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["web-designer", "agent-b"],
            "max_task_attempts": 3,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert "web-designer" not in summary
    assert "- succeeded: @agent-b - Work" in summary


async def test_orchestrator_all_fallback_attempts_fail_still_done() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [StreamChunk(event_type="error", error_code="boom", error="first failed")],
    )
    adapter_b = FakeSubAdapter(
        "agent-b",
        [StreamChunk(event_type="error", error_code="boom", error="second failed")],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Work", "Do work")],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["agent-b"],
            "max_task_attempts": 2,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- failed: @agent-b - Work" in summary
    assert "attempt 1 @agent-a: failed - first failed" in summary
    assert "attempt 2 @agent-b: failed - second failed" in summary


async def test_orchestrator_requires_task_plan_or_emits_clear_error() -> None:
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    missing_tasks = await _collect(orchestrator, config={"sub_adapters": {}})
    assert [chunk.event_type for chunk in missing_tasks] == ["start", "error"]
    assert missing_tasks[1].error_code == "missing_task_plan"

    missing_adapters = await _collect(
        orchestrator,
        config={"tasks": [_task("task-a", "agent-a", "Backend API", "Build API")]},
    )
    assert [chunk.event_type for chunk in missing_adapters] == ["start", "error"]
    assert missing_adapters[1].error_code == "missing_sub_adapters"


async def test_orchestrator_intercepts_subagent_error_chunk() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Build API")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and chunk.agent_id == "agent-a"
        and chunk.text_delta == "failed: too many requests\n"
        for chunk in chunks
    )
    assert any("- failed: @agent-a - Backend API" in (chunk.text_delta or "") for chunk in chunks)


async def test_orchestrator_continues_after_subagent_stream_exception() -> None:
    adapter_a = FakePartialThenExceptionAdapter(
        "agent-a",
        [
            StreamChunk(
                event_type="block_start", block_index=0, block_type="text"
            ),
            StreamChunk(
                event_type="delta", block_index=0, text_delta="partial from a"
            ),
        ],
        RuntimeError("upstream connection lost"),
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(chunk.text_delta == "partial from a" for chunk in chunks)
    assert any(
        chunk.event_type == "delta"
        and chunk.agent_id == "agent-a"
        and chunk.text_delta == "failed: upstream connection lost\n"
        for chunk in chunks
    )
    assert any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- succeeded: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )
    _assert_blocks_balanced(chunks)


async def test_orchestrator_continues_after_subagent_error_chunk() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and chunk.agent_id == "agent-a"
        and chunk.text_delta == "failed: too many requests\n"
        for chunk in chunks
    )
    assert any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- succeeded: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_skips_tasks_with_failed_dependencies() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task(
                    "task-b",
                    "agent-b",
                    "Frontend UI",
                    "Build UI",
                    depends_on=["task-a"],
                ),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert not any(
        chunk.event_type == "agent_switch" and chunk.to_agent == "agent-b"
        for chunk in chunks
    )
    assert not any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- skipped: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_all_tasks_fail_still_done() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    adapter_b = FakeSubAdapter(
        "agent-b",
        [
            StreamChunk(event_type="start", agent_id="agent-b"),
            StreamChunk(
                event_type="error",
                agent_id="agent-b",
                error_code="timeout",
                error="connection timeout",
            ),
        ],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- failed: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_adapter_factory_exception_is_task_failure() -> None:
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))

    def adapter_factory(agent_id: str) -> BaseAgentAdapter:
        if agent_id == "agent-a":
            raise RuntimeError("factory broken")
        return adapter_b

    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "adapter_factory": adapter_factory,
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and chunk.agent_id == "agent-a"
        and chunk.text_delta == "failed: factory broken\n"
        for chunk in chunks
    )
    assert any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- succeeded: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_fallback_adapter_handles_invalid_task_plan() -> None:
    fallback = FakeSubAdapter("fallback", _text_chunks("fallback result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": "invalid task plan",
            "fallback_agent_id": "claude-code",
            "fallback_adapter": fallback,
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and "Task plan unavailable; falling back to @claude-code." in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        chunk.event_type == "agent_switch"
        and chunk.to_agent == "claude-code"
        and chunk.task == "fallback"
        for chunk in chunks
    )
    assert any(chunk.text_delta == "fallback result" for chunk in chunks)
    assert any(
        "- fallback: single agent mode" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_does_not_fallback_when_adapter_source_missing() -> None:
    fallback = FakeSubAdapter("fallback", _text_chunks("fallback result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Build API")],
            "fallback_agent_id": "claude-code",
            "fallback_adapter": fallback,
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "missing_sub_adapters"
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert fallback.received_messages == []


async def test_orchestrator_rejects_duplicate_task_ids() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-a", "agent-a", "Review API", "Review API"),
            ],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "invalid_task_plan"
    assert "duplicate task_id" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_fallback_closes_open_block_on_exception() -> None:
    fallback = FakePartialThenExceptionAdapter(
        "fallback",
        [
            StreamChunk(
                event_type="block_start", block_index=0, block_type="text"
            ),
            StreamChunk(
                event_type="delta", block_index=0, text_delta="partial fallback"
            ),
        ],
        RuntimeError("fallback crashed"),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": "invalid task plan",
            "fallback_agent_id": "claude-code",
            "fallback_adapter": fallback,
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(chunk.text_delta == "partial fallback" for chunk in chunks)
    assert any(
        chunk.event_type == "delta"
        and chunk.agent_id == "claude-code"
        and chunk.text_delta == "failed: fallback crashed\n"
        for chunk in chunks
    )
    _assert_blocks_balanced(chunks)


async def test_registry_returns_orchestrator_adapter_for_builtin_orchestrator() -> None:
    class FakeDb:
        async def get(self, model: object, key: str) -> Agent | None:
            assert model is Agent
            if key != "orchestrator":
                return None
            return Agent(
                id="orchestrator",
                user_id=None,
                name="Orchestrator",
                provider="builtin",
                avatar_url="/avatars/orchestrator.png",
                capabilities=["task_decomposition", "coordination"],
                system_prompt="Coordinate sub agents.",
                config={"model_backend": "claude"},
                is_builtin=True,
            )

    adapter = await get_adapter("orchestrator", FakeDb())  # type: ignore[arg-type]

    assert isinstance(adapter, OrchestratorAdapter)
    assert callable(adapter.default_config["adapter_factory"])
    assert adapter.default_config["managed_agent_ids"]
    assert adapter.default_config["llm_planning"] is True
    assert adapter.default_config["orchestrator_parallel_enabled"] is True
    assert adapter.default_config["react_enabled"] is True
    assert adapter.default_config["planner_model_backend"] == "claude"
