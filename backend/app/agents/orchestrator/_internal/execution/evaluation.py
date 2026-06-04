"""Attempt evaluation orchestration and workflow dry-run side effects."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from app.agents.orchestrator._internal.memory import (
    record_event as _memory_record_event,
)
from app.agents.orchestrator.evaluation import (
    evaluate_attempt as _evaluate_attempt,
)
from app.agents.orchestrator.evaluation import (
    evaluation_results_payload as _evaluation_results_payload,
)
from app.agents.orchestrator.evaluation import (
    reflection_payload as _reflection_payload,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskState,
)
from app.services.workspace_workflow_runtime import (
    WorkspaceWorkflowRuntimeService,
)


async def run_attempt_evaluation(
    config: Mapping[str, Any],
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
    agent_id: str,
) -> None:
    if config.get("orchestrator_evaluation_enabled", True) is False:
        return
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_started",
        task_id=task.task_id,
        agent_id=agent_id,
        payload={
            "attempt_index": attempt.attempt_index,
            "artifact_paths": attempt.artifact_paths,
        },
    )
    outcome = await _evaluate_attempt(config, task, attempt, workspace_path)
    attempt.evaluation_results = list(outcome.results)
    await run_workflow_dry_runs(config, task, attempt, run_context, agent_id)
    attempt.reflection = outcome.reflection
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_result",
        task_id=task.task_id,
        agent_id=agent_id,
        payload={
            "attempt_index": attempt.attempt_index,
            "results": _evaluation_results_payload(attempt.evaluation_results),
        },
    )
    if outcome.reflection is not None:
        reflection = _reflection_payload(outcome.reflection)
        await _memory_record_event(
            config,
            run_context,
            event_type="reflection_created",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "attempt_index": attempt.attempt_index,
                "reflection": reflection,
            },
        )
        if outcome.failed:
            attempt.state = TaskState.EVALUATION_FAILED
            attempt.error = (
                str(reflection.get("repair_instruction"))
                if reflection
                else "evaluation failed"
            )
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_finished",
        task_id=task.task_id,
        agent_id=agent_id,
        payload={
            "attempt_index": attempt.attempt_index,
            "status": attempt.state.value,
        },
    )


async def run_workflow_dry_runs(
    config: Mapping[str, Any],
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    agent_id: str,
) -> None:
    paths = workflow_validation_passed_paths(attempt.evaluation_results)
    if not paths:
        return
    db = config.get("orchestrator_db_session")
    conversation_id = config.get("conversation_id")
    if not isinstance(conversation_id, UUID) or db is None:
        return
    service_raw = config.get("orchestrator_workflow_runtime_service")
    service = (
        service_raw
        if isinstance(service_raw, WorkspaceWorkflowRuntimeService)
        else WorkspaceWorkflowRuntimeService()
    )
    for path in paths:
        try:
            lock = config.get("orchestrator_workflow_runtime_lock")
            if lock is None:
                run = await service.dry_run(db, conversation_id, path=path, inputs={})
            else:
                async with cast(Any, lock):
                    run = await service.dry_run(db, conversation_id, path=path, inputs={})
            payload = {
                "evaluator": "workflow_dry_run",
                "status": "passed" if run.status == "passed" else "failed",
                "passed": run.status == "passed",
                "severity": "info" if run.status == "passed" else "major",
                "issues": []
                if run.status == "passed"
                else [
                    {
                        "code": "workflow_dry_run_failed",
                        "message": run.error or "workflow dry-run failed",
                        "evidence": path,
                        "repair_hint": "Fix the workflow runtime nodes or assertions.",
                    }
                ],
                "checked_artifacts": [path],
                "run_id": str(run.id),
                "dry_run_status": run.dry_run_status,
                "health_status": run.health_status,
            }
            attempt.evaluation_results.append(payload)
            await _memory_record_event(
                config,
                run_context,
                event_type="workflow_dry_run_completed",
                task_id=task.task_id,
                agent_id=agent_id,
                payload={
                    "path": path,
                    "run_id": str(run.id),
                    "status": run.status,
                    "runtime_status": run.runtime_status,
                    "dry_run_status": run.dry_run_status,
                    "health_status": run.health_status,
                    "node_results": run.node_results,
                },
            )
            if run.status != "passed":
                attempt.state = TaskState.EVALUATION_FAILED
                attempt.error = run.error or "workflow dry-run failed"
        except Exception as exc:  # noqa: BLE001
            attempt.evaluation_results.append(
                {
                    "evaluator": "workflow_dry_run",
                    "status": "failed",
                    "passed": False,
                    "severity": "major",
                    "issues": [
                        {
                            "code": "workflow_dry_run_error",
                            "message": str(exc),
                            "evidence": path,
                            "repair_hint": "Fix the workflow artifact and rerun dry-run.",
                        }
                    ],
                    "checked_artifacts": [path],
                    "dry_run_status": "failed",
                    "health_status": "failed",
                }
            )
            attempt.state = TaskState.EVALUATION_FAILED
            attempt.error = str(exc)


def workflow_validation_passed_paths(results: list[Any]) -> list[str]:
    paths: list[str] = []
    for payload in _evaluation_results_payload(results):
        if payload.get("evaluator") != "workflow_validation":
            continue
        if payload.get("passed") is not True or payload.get("status") != "passed":
            continue
        checked = payload.get("checked_artifacts")
        if isinstance(checked, list):
            paths.extend(item for item in checked if isinstance(item, str) and item)
    return list(dict.fromkeys(paths))
