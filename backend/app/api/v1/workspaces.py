"""Workspace Artifact API routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DbSession, get_current_user
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.workspace import (
    WorkspacePreviewRequest,
    WorkspacePreviewResponse,
    WorkspacePreviewVerifyRequest,
    WorkspacePreviewVerifyResponse,
    WorkspaceTreeResponse,
)
from app.services.browser_preview_verifier import (
    BrowserPreviewVerifier,
    BrowserPreviewVerifyDisabledError,
    BrowserPreviewVerifyError,
)
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

router = APIRouter()
workspace_service = WorkspaceService()
preview_service = WorkspacePreviewService(workspace_service)
browser_verifier = BrowserPreviewVerifier()


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


async def _get_owned_conversation_or_404(
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    conversation = (await db.execute(stmt)).scalar_one_or_none()
    if conversation is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "CONVERSATION_NOT_FOUND",
            "Conversation not found",
        )
    return conversation


def _map_workspace_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceViolation):
        return _error(
            status.HTTP_403_FORBIDDEN,
            "workspace_violation",
            str(exc),
        )
    if isinstance(exc, WorkspaceFileNotFound):
        return _error(
            status.HTTP_404_NOT_FOUND,
            "workspace_file_not_found",
            str(exc),
        )
    if isinstance(exc, WorkspaceFileTooLarge):
        return _error(
            413,
            "workspace_file_too_large",
            str(exc),
        )
    raise exc


def _map_preview_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspacePreviewDisabledError):
        return _error(
            status.HTTP_403_FORBIDDEN,
            "workspace_preview_disabled",
            str(exc),
        )
    if isinstance(exc, WorkspacePreviewStartError):
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "workspace_preview_start_failed",
            str(exc),
        )
    return _map_workspace_error(exc)


def _map_browser_verify_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BrowserPreviewVerifyDisabledError):
        return _error(
            status.HTTP_403_FORBIDDEN,
            "browser_preview_verify_disabled",
            str(exc),
        )
    if isinstance(exc, BrowserPreviewVerifyError):
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "browser_preview_verify_failed",
            str(exc),
        )
    raise exc


def _file_headers(mime_type: str) -> dict[str, str]:
    headers = {"X-Content-Type-Options": "nosniff"}
    if mime_type == "text/html":
        headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline'; sandbox"
        headers["X-Frame-Options"] = "SAMEORIGIN"
    return headers


@router.get(
    "/{conversation_id}/tree",
    response_model=WorkspaceTreeResponse,
    response_model_exclude_none=True,
)
async def get_workspace_tree(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    max_depth: int = Query(default=5, ge=0, le=20),
) -> WorkspaceTreeResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    workspace = await workspace_service.get_or_create(db, conversation_id)
    tree = workspace_service.list_tree(workspace, max_depth=max_depth)
    return WorkspaceTreeResponse(root=workspace.root_path, tree=tree)


@router.get("/{conversation_id}/files/{path:path}")
async def read_workspace_file(
    conversation_id: UUID,
    path: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    workspace = await workspace_service.get_or_create(db, conversation_id)
    try:
        content, mime_type = workspace_service.read_file(workspace, path)
    except (WorkspaceViolation, WorkspaceFileNotFound, WorkspaceFileTooLarge) as exc:
        raise _map_workspace_error(exc) from exc
    return Response(
        content=content,
        media_type=mime_type,
        headers=_file_headers(mime_type),
    )


@router.post(
    "/{conversation_id}/preview",
    response_model=WorkspacePreviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_workspace_preview(
    conversation_id: UUID,
    payload: WorkspacePreviewRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspacePreviewResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    try:
        session = await preview_service.start(
            db,
            conversation_id,
            entry_path=payload.entry_path,
            requested_port=payload.requested_port,
        )
    except (
        WorkspacePreviewDisabledError,
        WorkspacePreviewStartError,
        WorkspaceViolation,
        WorkspaceFileNotFound,
        WorkspaceFileTooLarge,
    ) as exc:
        raise _map_preview_error(exc) from exc
    return WorkspacePreviewResponse.model_validate(session)


@router.post(
    "/{conversation_id}/preview/verify",
    response_model=WorkspacePreviewVerifyResponse,
)
async def verify_workspace_preview(
    conversation_id: UUID,
    payload: WorkspacePreviewVerifyRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspacePreviewVerifyResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    session = await preview_service.get(db, conversation_id)
    if session is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "workspace_preview_not_found",
            "workspace preview session not found",
        )
    if session.status != "running":
        raise _error(
            status.HTTP_409_CONFLICT,
            "workspace_preview_not_running",
            "workspace preview session is not running",
        )
    try:
        result = await browser_verifier.verify(
            conversation_id=conversation_id,
            url=session.url,
            required_text=payload.required_text,
            viewports=payload.viewports,
            click_buttons=payload.click_buttons,
            max_clicks=payload.max_clicks,
        )
    except (BrowserPreviewVerifyDisabledError, BrowserPreviewVerifyError) as exc:
        raise _map_browser_verify_error(exc) from exc
    return WorkspacePreviewVerifyResponse.model_validate(result)


@router.get(
    "/{conversation_id}/preview",
    response_model=WorkspacePreviewResponse,
)
async def get_workspace_preview(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspacePreviewResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    session = await preview_service.get(db, conversation_id)
    if session is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "workspace_preview_not_found",
            "workspace preview session not found",
        )
    return WorkspacePreviewResponse.model_validate(session)


@router.delete(
    "/{conversation_id}/preview",
    response_model=WorkspacePreviewResponse,
)
async def stop_workspace_preview(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspacePreviewResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    session = await preview_service.stop(db, conversation_id)
    if session is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "workspace_preview_not_found",
            "workspace preview session not found",
        )
    return WorkspacePreviewResponse.model_validate(session)


@router.put("/{conversation_id}/files/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def write_workspace_file(
    conversation_id: UUID,
    path: str,
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    content = await request.body()
    if len(content) > settings.workspace_max_read_bytes:
        raise _error(
            413,
            "workspace_file_too_large",
            "workspace file too large",
        )
    workspace = await workspace_service.get_or_create(db, conversation_id)
    try:
        workspace_service.write_file(workspace, path, content)
    except (WorkspaceViolation, WorkspaceFileNotFound, WorkspaceFileTooLarge) as exc:
        raise _map_workspace_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
