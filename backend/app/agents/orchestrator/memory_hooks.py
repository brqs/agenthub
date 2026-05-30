"""No-op-safe structured memory hooks for Orchestrator execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from app.agents.orchestrator.types import (
    OrchestratorMemoryWriter,
    OrchestratorRunContext,
    SubTask,
    TaskResult,
)


async def start_run(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    *,
    user_request: str,
    plan_source: str,
    tasks: list[SubTask],
) -> None:
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        run_context.memory_run_id = await writer.start_run(
            user_request=user_request,
            plan_source=plan_source,
            tasks=tasks,
        )
    except Exception:  # noqa: BLE001
        run_context.memory_run_id = None


async def record_task_started(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    task: SubTask,
    agent_id: str,
    attempt_index: int,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        await writer.record_task_started(
            run_id=run_context.memory_run_id,
            task=task,
            agent_id=agent_id,
            attempt_index=attempt_index,
        )
    except Exception:  # noqa: BLE001
        return


async def record_task_result(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    task: SubTask,
    result: TaskResult,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        await writer.record_task_result(
            run_id=run_context.memory_run_id,
            task=task,
            result=result,
        )
    except Exception:  # noqa: BLE001
        return


async def finish_run(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    status: str,
    final_summary: str,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        await writer.finish_run(
            run_id=run_context.memory_run_id,
            status=status,
            final_summary=final_summary,
        )
    except Exception:  # noqa: BLE001
        return


def _memory_writer(config: Mapping[str, Any]) -> OrchestratorMemoryWriter | None:
    writer = config.get("orchestrator_memory_writer")
    if writer is None:
        return None
    return cast(OrchestratorMemoryWriter, writer)
