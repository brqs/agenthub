"""Public read-only routes for immutable workspace static releases."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.deps import DbSession
from app.models.workspace import WorkspaceDeployment
from app.services.workspace.static_server import HTML_CSP

router = APIRouter(prefix="/releases", tags=["Releases"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="release not found")


@router.get("/{release_token}")
@router.get("/{release_token}/{path:path}")
async def read_release(
    release_token: str,
    db: DbSession,
    request: Request,
    path: str = "",
) -> Response:
    """Return a static release file or proxy a published container release."""
    stmt = select(WorkspaceDeployment).where(
        WorkspaceDeployment.release_token == release_token,
        WorkspaceDeployment.status == "published",
    )
    deployment = (await db.execute(stmt)).scalar_one_or_none()
    if deployment is not None and deployment.kind == "container":
        return await _proxy_container_release(deployment, path, request)
    if deployment is None or deployment.kind != "static_site":
        raise _not_found()
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


async def _proxy_container_release(
    deployment: WorkspaceDeployment,
    path: str,
    request: Request,
) -> Response:
    if deployment.host_port is None:
        raise _not_found()
    relative_text = path.strip("/")
    relative = Path(relative_text)
    if relative.is_absolute() or PureWindowsPath(relative_text).is_absolute():
        raise _not_found()
    if ".." in relative.parts:
        raise _not_found()
    local_path = f"/{relative.as_posix()}" if relative_text else "/"
    target_url = f"http://127.0.0.1:{deployment.host_port}{local_path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            proxied = await client.get(target_url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="container release is unavailable",
        ) from exc
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    content_type = proxied.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type
    return Response(
        content=proxied.content,
        status_code=proxied.status_code,
        headers=headers,
    )
