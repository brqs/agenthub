"""Queueable deployment worker dispatch and in-process container runner."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.workspace import Workspace, WorkspaceDeployment
from app.services.workspace_container_release import (
    ContainerDeploymentCancelledError,
    ContainerDeploymentError,
    ContainerDeployWorker,
    ContainerPolicyError,
)
from app.services.workspace_service import WorkspaceFileTooLarge, WorkspaceViolation

BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


class DeploymentWorker(Protocol):
    """Marker protocol for platform-owned deployment workers."""


@dataclass(frozen=True)
class ContainerDeploymentOptions:
    """Queue-safe container deployment options."""

    container_port: int | None = None
    health_path: str = "/"


class ContainerDeploymentDispatcher(Protocol):
    """Queueable dispatch contract for container deployments."""

    async def submit_container_deployment(
        self,
        deployment_id: UUID,
        conversation_id: UUID,
        workspace_id: UUID,
        options: ContainerDeploymentOptions,
    ) -> str:
        """Queue or start a container deployment worker and return its worker id."""


class InProcessContainerDeploymentDispatcher:
    """Default MVP dispatcher that runs deployment work in this API process."""

    def __init__(
        self,
        *,
        container_worker: ContainerDeployWorker | None = None,
        startup_delay_seconds: float = 0.05,
    ) -> None:
        self._container_worker = container_worker or ContainerDeployWorker()
        self._startup_delay_seconds = startup_delay_seconds

    async def submit_container_deployment(
        self,
        deployment_id: UUID,
        conversation_id: UUID,
        workspace_id: UUID,
        options: ContainerDeploymentOptions,
    ) -> str:
        worker_id = f"inproc-container-{uuid4().hex[:12]}"
        task = asyncio.create_task(
            self._run_after_commit(
                deployment_id,
                conversation_id,
                workspace_id,
                options,
                worker_id,
            )
        )
        BACKGROUND_TASKS.add(task)
        task.add_done_callback(BACKGROUND_TASKS.discard)
        return worker_id

    async def _run_after_commit(
        self,
        deployment_id: UUID,
        conversation_id: UUID,
        workspace_id: UUID,
        options: ContainerDeploymentOptions,
        worker_id: str,
    ) -> None:
        await asyncio.sleep(self._startup_delay_seconds)
        try:
            async with SessionFactory() as db:
                deployment = await _wait_for_deployment(db, deployment_id)
                if deployment is None:
                    return
                if deployment.status == "stopped":
                    return
                await run_container_deployment_worker(
                    db,
                    deployment,
                    conversation_id=conversation_id,
                    workspace_id=workspace_id,
                    options=options,
                    worker_id=worker_id,
                    container_worker=self._container_worker,
                )
                await db.commit()
        except Exception as exc:
            await _mark_worker_unhandled_exception(deployment_id, worker_id, exc)


async def submit_container_deployment(
    deployment_id: UUID,
    conversation_id: UUID,
    workspace_id: UUID,
    options: ContainerDeploymentOptions,
) -> str:
    """Submit a container deployment through the default in-process dispatcher."""
    return await InProcessContainerDeploymentDispatcher().submit_container_deployment(
        deployment_id,
        conversation_id,
        workspace_id,
        options,
    )


async def run_container_deployment_worker(
    db: AsyncSession,
    deployment: WorkspaceDeployment,
    *,
    conversation_id: UUID,
    workspace_id: UUID,
    options: ContainerDeploymentOptions,
    worker_id: str,
    container_worker: ContainerDeployWorker,
) -> None:
    """Advance one queued container deployment to a terminal state."""
    if deployment.conversation_id != conversation_id or deployment.workspace_id != workspace_id:
        return
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        _mark_failed(
            deployment,
            "Workspace not found for deployment.",
            failure_category="policy_rejected",
            last_error_code="workspace_not_found",
        )
        await db.flush()
        return
    now = datetime.now(UTC)
    deployment.worker_id = worker_id
    deployment.attempt_count = (deployment.attempt_count or 0) + 1
    deployment.status = "publishing"
    deployment.runtime_status = "building"
    deployment.started_at = deployment.started_at or now
    deployment.logs = [*deployment.logs, "Container worker started."]
    _append_event(
        deployment,
        "status_changed",
        {"from": "queued", "to": "publishing", "worker_id": worker_id},
    )
    _touch(deployment)
    await db.flush()
    await db.commit()

    async def event_sink(event_type: str, payload: dict[str, object]) -> None:
        await db.refresh(deployment)
        if deployment.status == "stopped":
            return
        _append_event(deployment, event_type, payload)
        if payload.get("step") in {"build", "run", "health"}:
            deployment.runtime_status = str(payload["step"])
        _touch(deployment)
        await db.flush()
        await db.commit()

    async def cancellation_checker() -> bool:
        status = (
            await db.execute(
                select(WorkspaceDeployment.status).where(
                    WorkspaceDeployment.id == deployment.id
                )
            )
        ).scalar_one_or_none()
        return status == "stopped"

    try:
        if _worker_supports_hooks(container_worker):
            result = await container_worker.publish(
                Path(workspace.root_path),
                deployment.id,
                container_port=options.container_port,
                health_path=options.health_path,
                event_sink=event_sink,
                cancellation_checker=cancellation_checker,
            )
        else:
            result = await container_worker.publish(
                Path(workspace.root_path),
                deployment.id,
                container_port=options.container_port,
                health_path=options.health_path,
            )
    except ContainerDeploymentCancelledError:
        await db.refresh(deployment)
        deployment.status = "stopped"
        deployment.runtime_status = "stopped"
        deployment.stopped_at = deployment.stopped_at or datetime.now(UTC)
        deployment.completed_at = deployment.stopped_at
        deployment.logs = [*deployment.logs, "Container deployment stopped before publishing."]
        _append_event(deployment, "stopped", {"worker_id": worker_id})
        _touch(deployment)
        await db.flush()
        return
    except (
        ContainerDeploymentError,
        ContainerPolicyError,
        WorkspaceViolation,
        WorkspaceFileTooLarge,
        OSError,
    ) as exc:
        await db.refresh(deployment)
        if deployment.status == "stopped":
            deployment.runtime_status = "stopped"
            deployment.completed_at = datetime.now(UTC)
            _touch(deployment)
            await db.flush()
            return
        category, error_code = _classify_failure(exc)
        _mark_failed(
            deployment,
            str(exc),
            failure_category=category,
            last_error_code=error_code,
        )
        await db.flush()
        return

    await db.refresh(deployment)
    if deployment.status == "stopped":
        await container_worker.remove(
            container_id=result.container_id,
            image_id=result.image_id,
            snapshot_path=result.snapshot_path,
        )
        deployment.runtime_status = "stopped"
        deployment.completed_at = datetime.now(UTC)
        _touch(deployment)
        await db.flush()
        return
    now = datetime.now(UTC)
    deployment.status = "published"
    deployment.url = result.url
    deployment.healthcheck_url = result.healthcheck_url
    deployment.runtime_id = result.runtime_id
    deployment.image_id = result.image_id
    deployment.container_id = result.container_id
    deployment.host_port = result.host_port
    deployment.container_port = result.container_port
    deployment.runtime_kind = result.runtime_kind
    deployment.runtime_status = result.runtime_status
    deployment.logs_tail = result.logs_tail
    deployment.snapshot_path = str(result.snapshot_path)
    deployment.published_at = now
    deployment.completed_at = now
    deployment.last_checked_at = now
    deployment.failure_category = None
    deployment.last_error_code = None
    deployment.logs = [
        *deployment.logs,
        f"Container published at {result.url}.",
        f"Health check passed at {result.healthcheck_url}.",
    ]
    _append_event(
        deployment,
        "status_changed",
        {"from": "publishing", "to": "published", "worker_id": worker_id},
    )
    _touch(deployment)
    await db.flush()


async def mark_stale_container_deployments(db: AsyncSession) -> int:
    """Fail stale queued/publishing container deployments left by a dead worker."""
    now = datetime.now(UTC)
    timeout_seconds = max(
        settings.deployment_container_health_timeout_seconds * 3,
        settings.deployment_container_max_runtime_seconds,
        60,
    )
    rows = list(
        (
            await db.execute(
                select(WorkspaceDeployment).where(
                    WorkspaceDeployment.kind == "container",
                    WorkspaceDeployment.status.in_(["queued", "publishing"]),
                )
            )
        )
        .scalars()
        .all()
    )
    stale = [
        item
        for item in rows
        if (item.started_at or item.queued_at or item.created_at).timestamp()
        <= now.timestamp() - timeout_seconds
    ]
    for deployment in stale:
        _mark_failed(
            deployment,
            "Container deployment worker timed out before reaching a terminal state.",
            failure_category="timeout",
            last_error_code="worker_stale_timeout",
        )
    if stale:
        await db.flush()
    return len(stale)


async def _wait_for_deployment(
    db: AsyncSession,
    deployment_id: UUID,
) -> WorkspaceDeployment | None:
    for _ in range(100):
        deployment = await db.get(WorkspaceDeployment, deployment_id)
        if deployment is not None:
            return deployment
        await asyncio.sleep(0.05)
    return None


async def _mark_worker_unhandled_exception(
    deployment_id: UUID,
    worker_id: str,
    exc: Exception,
) -> None:
    async with SessionFactory() as db:
        deployment = await db.get(WorkspaceDeployment, deployment_id)
        if deployment is None or deployment.status not in {"queued", "publishing"}:
            return
        error = f"Container deployment worker crashed: {exc.__class__.__name__}: {exc}"
        _mark_failed(
            deployment,
            error,
            failure_category="runtime_unavailable",
            last_error_code="worker_unhandled_exception",
        )
        _append_event(
            deployment,
            "worker_unhandled_exception",
            {
                "worker_id": worker_id,
                "error_category": exc.__class__.__name__,
                "error_summary": str(exc)[:500],
            },
        )
        await db.flush()
        await db.commit()


def _mark_failed(
    deployment: WorkspaceDeployment,
    error: str,
    *,
    failure_category: str,
    last_error_code: str,
) -> None:
    now = datetime.now(UTC)
    deployment.status = "failed"
    deployment.error = error
    deployment.runtime_status = "failed"
    deployment.completed_at = now
    deployment.last_checked_at = now
    deployment.failure_category = failure_category
    deployment.last_error_code = last_error_code
    deployment.logs = [*deployment.logs, f"Container deployment failed: {error}"]
    deployment.logs_tail = error
    _append_event(
        deployment,
        "status_changed",
        {
            "to": "failed",
            "failure_category": failure_category,
            "last_error_code": last_error_code,
            "error_summary": error[:500],
        },
    )
    _touch(deployment)


def _append_event(
    deployment: WorkspaceDeployment,
    event_type: str,
    payload: dict[str, object],
) -> None:
    event = {
        "type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        **payload,
    }
    deployment.state_events = [*(deployment.state_events or []), event][-100:]


def _touch(deployment: WorkspaceDeployment) -> None:
    deployment.updated_at = datetime.now(UTC)


def _classify_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, ContainerPolicyError):
        return "policy_rejected", "container_policy_rejected"
    if isinstance(exc, WorkspaceFileTooLarge):
        return "policy_rejected", "container_snapshot_too_large"
    if isinstance(exc, WorkspaceViolation):
        return "policy_rejected", "container_workspace_violation"
    if isinstance(exc, FileNotFoundError):
        return "runtime_unavailable", "container_runtime_unavailable"
    message = str(exc).lower()
    if "port pool" in message and "exhausted" in message:
        return "port_pool_exhausted", "container_port_pool_exhausted"
    if "health check" in message:
        return "health_check_failed", "container_health_check_failed"
    if "run failed" in message:
        return "run_failed", "container_run_failed"
    if "build failed" in message or "dockerfile" in message:
        return "build_failed", "container_build_failed"
    if "timed out" in message or "timeout" in message:
        return "timeout", "container_deployment_timeout"
    if isinstance(exc, OSError):
        return "runtime_unavailable", "container_runtime_unavailable"
    return "run_failed", "container_deployment_failed"


def _worker_supports_hooks(container_worker: ContainerDeployWorker) -> bool:
    parameters = inspect.signature(container_worker.publish).parameters
    return "event_sink" in parameters and "cancellation_checker" in parameters
