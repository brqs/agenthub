"""Platform-managed workspace deployment and source export service."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.workspace import WorkspaceDeployment
from app.services.workspace_preview import (
    WorkspacePreviewDisabledError,
    WorkspacePreviewService,
    WorkspacePreviewStartError,
)
from app.services.workspace_service import (
    WorkspaceFileNotFound,
    WorkspaceFileTooLarge,
    WorkspaceService,
    WorkspaceViolation,
)

DEPLOYMENT_KINDS = {"static_site", "source_zip", "container"}
DEPLOYMENT_STATUSES = {
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


class WorkspaceDeploymentService:
    """Create, query, stop, and export platform-owned workspace deployments."""

    def __init__(
        self,
        workspace_service: WorkspaceService | None = None,
        preview_service: WorkspacePreviewService | None = None,
    ) -> None:
        self._workspace_service = workspace_service or WorkspaceService()
        self._preview_service = preview_service or WorkspacePreviewService(
            self._workspace_service
        )

    async def create(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        kind: str,
        entry_path: str | None = None,
        requested_port: int | None = None,
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
        return await self.create_container_placeholder(db, conversation_id)

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
            logs=["Validated static HTML entry.", "Starting platform static preview."],
        )
        db.add(deployment)
        await db.flush()
        try:
            preview = await self._preview_service.start(
                db,
                conversation_id,
                entry_path=normalized_entry_path,
                requested_port=requested_port,
            )
        except (
            WorkspacePreviewDisabledError,
            WorkspacePreviewStartError,
            WorkspaceViolation,
            WorkspaceFileNotFound,
            WorkspaceFileTooLarge,
        ) as exc:
            deployment.status = "failed"
            deployment.error = str(exc)
            deployment.logs = [*deployment.logs, f"Deployment failed: {exc}"]
            self._touch(deployment)
            await db.flush()
            raise WorkspaceDeploymentError(str(exc)) from exc

        deployment.status = "published"
        deployment.url = preview.url
        deployment.logs = [
            *deployment.logs,
            f"Published static site at {preview.url}.",
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
            size_bytes = self._write_zip(Path(workspace.root_path), export_path)
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
        deployment.download_url = self.download_url(conversation_id, deployment.id)
        deployment.logs = [
            *deployment.logs,
            f"Source archive created with {size_bytes} bytes.",
        ]
        self._touch(deployment)
        await db.flush()
        return deployment

    async def create_container_placeholder(
        self,
        db: AsyncSession,
        conversation_id: UUID,
    ) -> WorkspaceDeployment:
        workspace = await self._workspace_service.get_or_create(db, conversation_id)
        deployment = WorkspaceDeployment(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            kind="container",
            status="not_supported",
            error="Container deployment is not supported by this platform yet.",
            logs=[
                "Container deployment request recorded.",
                "No Docker, shell, SSH, or external deployment command was executed.",
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
        if deployment.kind == "source_zip":
            self.export_path(conversation_id, deployment_id).unlink(missing_ok=True)
        deployment.status = "stopped"
        deployment.logs = [*deployment.logs, "Deployment marked as stopped."]
        self._touch(deployment)
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

    def _write_zip(self, workspace_root: Path, export_path: Path) -> int:
        root = workspace_root.resolve()
        total_bytes = 0
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
                total_bytes += stat.st_size
                if total_bytes > settings.deployment_max_export_bytes:
                    raise WorkspaceFileTooLarge("workspace source export is too large")
                archive.write(path, relative.as_posix())
        return export_path.stat().st_size

    def _is_excluded(self, relative: Path) -> bool:
        return any(part in SOURCE_EXPORT_EXCLUDED_PARTS for part in relative.parts)

    def _touch(self, deployment: WorkspaceDeployment) -> None:
        deployment.updated_at = datetime.now(UTC)
