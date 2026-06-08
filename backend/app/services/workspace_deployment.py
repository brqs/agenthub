"""Platform-managed workspace deployment and source export service."""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.workspace import WorkspaceDeployment
from app.services.workspace.container_release import (
    ContainerDeployWorker,
    ContainerPolicyValidator,
    current_container_policy,
)
from app.services.workspace.deployment_workers import (
    ContainerDeploymentDispatcher,
    ContainerDeploymentOptions,
    InProcessContainerDeploymentDispatcher,
    mark_stale_container_deployments,
)
from app.services.workspace.static_release import WorkspaceStaticReleaseService
from app.services.workspace_service import (
    WorkspaceFileNotFound,
    WorkspaceFileTooLarge,
    WorkspaceService,
    WorkspaceViolation,
)

DEPLOYMENT_KINDS = {"static_site", "source_zip", "container"}
DEPLOYMENT_STATUSES = {
    "queued",
    "publishing",
    "published",
    "failed",
    "stopped",
    "not_supported",
}
SOURCE_EXPORT_EXCLUDED_PARTS = {
    ".agenthub",
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".env",
    ".ssh",
    "secrets",
}


class WorkspaceDeploymentDisabledError(RuntimeError):
    """Raised when deployment features are disabled."""


class WorkspaceDeploymentError(RuntimeError):
    """Raised when a deployment request cannot be completed."""


class WorkspaceDeploymentNotFoundError(RuntimeError):
    """Raised when a deployment record is not found."""


def _container_runtime_available(runtime: str) -> bool:
    return shutil.which(runtime) is not None


class WorkspaceDeploymentService:
    """Create, query, stop, and export platform-owned workspace deployments."""

    def __init__(
        self,
        workspace_service: WorkspaceService | None = None,
        static_release_service: WorkspaceStaticReleaseService | None = None,
        container_worker: ContainerDeployWorker | None = None,
        container_dispatcher: ContainerDeploymentDispatcher | None = None,
        container_runtime_available: Callable[[str], bool] | None = None,
    ) -> None:
        self._workspace_service = workspace_service or WorkspaceService()
        self._static_release_service = static_release_service or WorkspaceStaticReleaseService()
        self._container_worker = container_worker or ContainerDeployWorker()
        self._container_dispatcher = (
            container_dispatcher
            or InProcessContainerDeploymentDispatcher(container_worker=self._container_worker)
        )
        self._container_policy_validator = ContainerPolicyValidator()
        if container_runtime_available is not None:
            self._container_runtime_available = container_runtime_available
        elif container_worker is not None or container_dispatcher is not None:
            self._container_runtime_available = lambda _runtime: True
        else:
            self._container_runtime_available = (
                lambda runtime: _container_runtime_available(runtime)
            )

    async def create(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        kind: str,
        entry_path: str | None = None,
        requested_port: int | None = None,
        container_port: int | None = None,
        health_path: str | None = None,
        start_command: str | None = None,
    ) -> WorkspaceDeployment:
        if not settings.deployment_enabled:
            raise WorkspaceDeploymentDisabledError("workspace deployment is disabled")
        if kind not in DEPLOYMENT_KINDS:
            raise WorkspaceDeploymentError(f"unsupported deployment kind: {kind}")
        if kind == "static_site":
            return await self.create_static_site(
                db,
                conversation_id,
                entry_path=entry_path,
                requested_port=requested_port,
            )
        if kind == "source_zip":
            return await self.package_source_zip(db, conversation_id)
        return await self.create_container(
            db,
            conversation_id,
            container_port=container_port,
            health_path=health_path,
            start_command=start_command,
        )

    async def create_static_site(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        entry_path: str | None,
        requested_port: int | None = None,
    ) -> WorkspaceDeployment:
        if not entry_path or not entry_path.strip():
            raise WorkspaceDeploymentError("entry_path is required for static_site")
        workspace = await self._workspace_service.get_or_create(db, conversation_id)
        entry = self._workspace_service.validate_read_path(
            Path(workspace.root_path),
            entry_path,
        )
        if entry.suffix.lower() not in {".html", ".htm"}:
            raise WorkspaceViolation(f"static_site entry must be an HTML file: {entry_path}")
        normalized_entry_path = entry.relative_to(Path(workspace.root_path)).as_posix()
        deployment = WorkspaceDeployment(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            kind="static_site",
            status="publishing",
            entry_path=normalized_entry_path,
            logs=["Validated static HTML entry.", "Creating immutable static release snapshot."],
        )
        db.add(deployment)
        await db.flush()
        try:
            snapshot, release_token, release_url = self._static_release_service.publish(
                Path(workspace.root_path),
                deployment.id,
                entry_path=normalized_entry_path,
            )
        except (WorkspaceViolation, WorkspaceFileNotFound, WorkspaceFileTooLarge, OSError) as exc:
            deployment.status = "failed"
            deployment.error = str(exc)
            deployment.logs = [*deployment.logs, f"Deployment failed: {exc}"]
            self._touch(deployment)
            await db.flush()
            raise WorkspaceDeploymentError(str(exc)) from exc

        deployment.status = "published"
        deployment.url = release_url
        deployment.release_token = release_token
        deployment.snapshot_path = str(snapshot.root)
        deployment.artifact_digest = snapshot.artifact_digest
        deployment.file_count = snapshot.file_count
        deployment.size_bytes = snapshot.size_bytes
        deployment.published_at = datetime.now(UTC)
        deployment.logs = [
            *deployment.logs,
            *(
                ["Ignored requested_port because static releases use the stable release route."]
                if requested_port is not None
                else []
            ),
            f"Published immutable static site at {release_url}.",
        ]
        self._touch(deployment)
        await db.flush()
        return deployment

    async def package_source_zip(
        self,
        db: AsyncSession,
        conversation_id: UUID,
    ) -> WorkspaceDeployment:
        if not settings.deployment_enabled:
            raise WorkspaceDeploymentDisabledError("workspace deployment is disabled")
        workspace = await self._workspace_service.get_or_create(db, conversation_id)
        deployment = WorkspaceDeployment(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            kind="source_zip",
            status="publishing",
            logs=["Packaging workspace source archive."],
        )
        db.add(deployment)
        await db.flush()
        export_path = self.export_path(conversation_id, deployment.id)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            size_bytes, file_count, artifact_digest = self._write_zip(
                Path(workspace.root_path), export_path
            )
        except (OSError, WorkspaceFileTooLarge) as exc:
            export_path.unlink(missing_ok=True)
            deployment.status = "failed"
            deployment.error = str(exc)
            deployment.logs = [*deployment.logs, f"Source archive failed: {exc}"]
            self._touch(deployment)
            await db.flush()
            raise WorkspaceDeploymentError(str(exc)) from exc
        deployment.status = "published"
        deployment.size_bytes = size_bytes
        deployment.file_count = file_count
        deployment.artifact_digest = artifact_digest
        deployment.published_at = datetime.now(UTC)
        deployment.expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.deployment_export_ttl_seconds
        )
        deployment.download_url = self.download_url(conversation_id, deployment.id)
        deployment.logs = [
            *deployment.logs,
            f"Source archive created with {size_bytes} bytes.",
        ]
        self._touch(deployment)
        await db.flush()
        return deployment

    async def create_container(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        container_port: int | None = None,
        health_path: str | None = None,
        start_command: str | None = None,
    ) -> WorkspaceDeployment:
        workspace = await self._workspace_service.get_or_create(db, conversation_id)
        now = datetime.now(UTC)
        if start_command:
            raise WorkspaceDeploymentError(
                "start_command is not supported for container deployment"
            )
        if not settings.deployment_container_enabled:
            return await self._create_container_not_supported(
                db,
                conversation_id,
                workspace.id,
                "Container deployment is disabled. Enable DEPLOYMENT_CONTAINER_ENABLED to use it.",
            )
        try:
            self._container_policy_validator.validate(current_container_policy())
        except Exception as exc:
            return await self._create_container_not_supported(
                db,
                conversation_id,
                workspace.id,
                str(exc),
            )
        if not self._container_runtime_available(settings.deployment_container_runtime):
            return await self._create_container_not_supported(
                db,
                conversation_id,
                workspace.id,
                (
                    "Container runtime is not available on this host: "
                    f"{settings.deployment_container_runtime}. Install/configure the runtime "
                    "or set DEPLOYMENT_CONTAINER_RUNTIME to an available runtime."
                ),
            )
        deployment = WorkspaceDeployment(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            kind="container",
            status="queued",
            container_port=container_port,
            runtime_kind=settings.deployment_container_runtime,
            queued_at=now,
            logs=[
                "Container deployment request accepted.",
                "Container deployment queued for platform worker.",
            ],
            state_events=[
                {
                    "type": "status_changed",
                    "timestamp": now.isoformat(),
                    "to": "queued",
                    "runtime_kind": settings.deployment_container_runtime,
                }
            ],
        )
        db.add(deployment)
        await db.flush()
        worker_id = await self._container_dispatcher.submit_container_deployment(
            deployment.id,
            conversation_id,
            workspace.id,
            ContainerDeploymentOptions(
                container_port=container_port,
                health_path=health_path or "/",
            ),
        )
        deployment.worker_id = worker_id
        deployment.logs = [*deployment.logs, f"Container worker submitted: {worker_id}."]
        deployment.state_events = [
            *deployment.state_events,
            {
                "type": "worker_submitted",
                "timestamp": datetime.now(UTC).isoformat(),
                "worker_id": worker_id,
            },
        ]
        self._touch(deployment)
        await db.flush()
        return deployment

    async def _create_container_not_supported(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        workspace_id: UUID,
        error: str,
    ) -> WorkspaceDeployment:
        deployment = WorkspaceDeployment(
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            kind="container",
            status="not_supported",
            error=error,
            runtime_kind=settings.deployment_container_runtime,
            logs=[
                "Container deployment request recorded.",
                "No Docker socket, shell, SSH, or external deployment command was executed.",
            ],
        )
        db.add(deployment)
        await db.flush()
        return deployment

    async def list(
        self,
        db: AsyncSession,
        conversation_id: UUID,
    ) -> list[WorkspaceDeployment]:
        stmt = (
            select(WorkspaceDeployment)
            .where(WorkspaceDeployment.conversation_id == conversation_id)
            .order_by(WorkspaceDeployment.created_at.desc())
        )
        return list((await db.execute(stmt)).scalars().all())

    async def get(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        deployment_id: UUID,
    ) -> WorkspaceDeployment | None:
        stmt = select(WorkspaceDeployment).where(
            WorkspaceDeployment.conversation_id == conversation_id,
            WorkspaceDeployment.id == deployment_id,
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def stop(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        deployment_id: UUID,
    ) -> WorkspaceDeployment | None:
        deployment = await self.get(db, conversation_id, deployment_id)
        if deployment is None:
            return None
        if deployment.status == "stopped":
            return deployment
        if deployment.kind == "source_zip":
            self.export_path(conversation_id, deployment_id).unlink(missing_ok=True)
        elif deployment.kind == "static_site":
            self._static_release_service.remove(deployment.snapshot_path, deployment.id)
            deployment.release_token = None
            deployment.snapshot_path = None
            deployment.url = None
        elif deployment.kind == "container":
            previous_status = deployment.status
            await self._container_worker.remove(
                container_id=deployment.container_id,
                image_id=deployment.image_id,
                snapshot_path=deployment.snapshot_path,
            )
            deployment.container_id = None
            deployment.runtime_id = None
            deployment.image_id = None
            deployment.host_port = None
            deployment.runtime_status = "stopped"
            deployment.release_token = None
            deployment.url = None
            deployment.healthcheck_url = None
        deployment.status = "stopped"
        deployment.stopped_at = datetime.now(UTC)
        deployment.logs = [*deployment.logs, "Deployment marked as stopped."]
        if deployment.kind == "container":
            deployment.state_events = [
                *(deployment.state_events or []),
                {
                    "type": "stop_requested"
                    if previous_status in {"queued", "publishing"}
                    else "status_changed",
                    "timestamp": deployment.stopped_at.isoformat(),
                    "from": previous_status,
                    "to": "stopped",
                },
            ]
        self._touch(deployment)
        await db.flush()
        return deployment

    async def retry(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        deployment_id: UUID,
    ) -> WorkspaceDeployment | None:
        previous = await self.get(db, conversation_id, deployment_id)
        if previous is None:
            return None
        if previous.status not in {"failed", "stopped", "not_supported"}:
            raise WorkspaceDeploymentError(
                "Only failed, stopped, or unsupported deployments can be retried"
            )
        deployment = await self.create(
            db,
            conversation_id,
            kind=previous.kind,
            entry_path=previous.entry_path,
            container_port=previous.container_port,
        )
        previous.logs = [
            *previous.logs,
            f"Retry requested; created deployment {deployment.id}.",
        ]
        self._touch(previous)
        await db.flush()
        return deployment

    def export_path(self, conversation_id: UUID, deployment_id: UUID) -> Path:
        return (
            Path(settings.deployment_export_dir).expanduser()
            / str(conversation_id)
            / f"{deployment_id}.zip"
        )

    def download_url(self, conversation_id: UUID, deployment_id: UUID) -> str:
        return (
            f"/api/v1/workspaces/{conversation_id}/deployments/"
            f"{deployment_id}/download"
        )

    async def cleanup_for_conversation(self, db: AsyncSession, conversation_id: UUID) -> None:
        """Remove all generated deployment resources for a conversation."""
        for deployment in await self.list(db, conversation_id):
            if deployment.kind == "source_zip":
                self.export_path(conversation_id, deployment.id).unlink(missing_ok=True)
            elif deployment.kind == "static_site":
                self._static_release_service.remove(deployment.snapshot_path, deployment.id)
                deployment.release_token = None
                deployment.snapshot_path = None
                deployment.url = None
            elif deployment.kind == "container":
                await self._container_worker.remove(
                    container_id=deployment.container_id,
                    image_id=deployment.image_id,
                    snapshot_path=deployment.snapshot_path,
                )
                deployment.container_id = None
                deployment.runtime_id = None
                deployment.runtime_status = "stopped"
                deployment.release_token = None
                deployment.url = None
                deployment.healthcheck_url = None
            deployment.status = "stopped"
            deployment.stopped_at = datetime.now(UTC)
            self._touch(deployment)
        shutil.rmtree(
            Path(settings.deployment_export_dir).expanduser() / str(conversation_id),
            ignore_errors=True,
        )
        await db.flush()

    async def cleanup_expired(self, db: AsyncSession) -> int:
        """Stop expired source exports and expired container runtimes."""
        now = datetime.now(UTC)
        stmt = select(WorkspaceDeployment).where(
            WorkspaceDeployment.kind == "source_zip",
            WorkspaceDeployment.status == "published",
            WorkspaceDeployment.expires_at.is_not(None),
            WorkspaceDeployment.expires_at <= now,
        )
        deployments = list((await db.execute(stmt)).scalars().all())
        for deployment in deployments:
            self.export_path(deployment.conversation_id, deployment.id).unlink(missing_ok=True)
            deployment.status = "stopped"
            deployment.stopped_at = now
            deployment.error = "Source archive expired and was removed."
            deployment.logs = [*deployment.logs, "Source archive expired and was removed."]
            self._touch(deployment)
        stale_count = await mark_stale_container_deployments(db)
        if deployments or stale_count:
            await db.flush()
        container_stmt = select(WorkspaceDeployment).where(
            WorkspaceDeployment.kind == "container",
            WorkspaceDeployment.status == "published",
            WorkspaceDeployment.started_at.is_not(None),
        )
        containers = list((await db.execute(container_stmt)).scalars().all())
        expired_containers = [
            item
            for item in containers
            if item.started_at
            and item.started_at
            + timedelta(seconds=settings.deployment_container_max_runtime_seconds)
            <= now
        ]
        for deployment in expired_containers:
            await self._container_worker.remove(
                container_id=deployment.container_id,
                image_id=deployment.image_id,
                snapshot_path=deployment.snapshot_path,
            )
            deployment.status = "stopped"
            deployment.stopped_at = now
            deployment.runtime_status = "stopped"
            deployment.url = None
            deployment.healthcheck_url = None
            deployment.error = "Container deployment expired and was stopped."
            deployment.logs = [*deployment.logs, "Container deployment expired and was stopped."]
            self._touch(deployment)
        if expired_containers:
            await db.flush()
        return len(deployments) + len(expired_containers) + stale_count

    async def cleanup_container_runtime_orphans(
        self,
        *,
        tracked_deployment_ids: set[str],
        tracked_container_ids: set[str],
        tracked_image_ids: set[str],
    ) -> None:
        await self._container_worker.cleanup_orphans(
            tracked_deployment_ids=tracked_deployment_ids,
            tracked_container_ids=tracked_container_ids,
            tracked_image_ids=tracked_image_ids,
        )

    def _write_zip(self, workspace_root: Path, export_path: Path) -> tuple[int, int, str]:
        root = workspace_root.resolve()
        total_bytes = 0
        file_count = 0
        with zipfile.ZipFile(
            export_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    continue
                if self._is_excluded(relative):
                    continue
                stat = path.stat()
                if stat.st_size > settings.deployment_max_single_file_bytes:
                    raise WorkspaceFileTooLarge(
                        f"workspace source export file is too large: {relative.as_posix()}"
                    )
                file_count += 1
                if file_count > settings.deployment_max_file_count:
                    raise WorkspaceFileTooLarge("workspace source export contains too many files")
                total_bytes += stat.st_size
                if total_bytes > settings.deployment_max_export_bytes:
                    raise WorkspaceFileTooLarge("workspace source export is too large")
                archive.write(path, relative.as_posix())
        digest = hashlib.sha256(export_path.read_bytes()).hexdigest()
        return export_path.stat().st_size, file_count, digest

    def _is_excluded(self, relative: Path) -> bool:
        return any(
            part in SOURCE_EXPORT_EXCLUDED_PARTS or part.startswith(".env.")
            for part in relative.parts
        )

    def _touch(self, deployment: WorkspaceDeployment) -> None:
        deployment.updated_at = datetime.now(UTC)
