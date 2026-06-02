"""Public read-only routes for immutable workspace static releases."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.deps import DbSession
from app.models.workspace import WorkspaceDeployment
from app.services.workspace_static_server import HTML_CSP

router = APIRouter(prefix="/releases", tags=["Releases"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="release not found")


@router.get("/{release_token}")
@router.get("/{release_token}/{path:path}")
async def read_static_release(
    release_token: str,
    db: DbSession,
    path: str = "",
) -> FileResponse:
    """Return one file from a published immutable release snapshot."""
    stmt = select(WorkspaceDeployment).where(
        WorkspaceDeployment.release_token == release_token,
        WorkspaceDeployment.kind == "static_site",
        WorkspaceDeployment.status == "published",
    )
    deployment = (await db.execute(stmt)).scalar_one_or_none()
    if deployment is None or not deployment.snapshot_path:
        raise _not_found()
    relative_text = path.strip("/") or deployment.entry_path or ""
    relative = Path(relative_text)
    if (
        not relative_text
        or relative.is_absolute()
        or PureWindowsPath(relative_text).is_absolute()
        or ".." in relative.parts
    ):
        raise _not_found()
    root = Path(deployment.snapshot_path).expanduser().resolve()
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise _not_found() from exc
    if not candidate.is_file() or candidate.is_symlink():
        raise _not_found()
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if candidate.suffix.lower() in {".html", ".htm"}:
        headers["Content-Security-Policy"] = HTML_CSP
    return FileResponse(candidate, headers=headers)
