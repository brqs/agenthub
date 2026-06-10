"""Workspace Artifact API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import ORCHESTRATOR_AGENT_ID
from app.api.v1.stream import _run_stream_session
from app.core.config import settings
from app.core.deps import DbSession, get_current_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.workspace import (
    WorkspaceArtifactListResponse,
    WorkspaceArtifactResponse,
    WorkspaceDeploymentListResponse,
    WorkspaceDeploymentRequest,
    WorkspaceDeploymentResponse,
    WorkspaceOneClickContainerDeploymentResponse,
    WorkspacePreviewRequest,
    WorkspacePreviewResponse,
    WorkspacePreviewVerifyRequest,
    WorkspacePreviewVerifyResponse,
    WorkspaceTreeResponse,
    WorkspaceWorkflowHealthResponse,
    WorkspaceWorkflowRunListResponse,
    WorkspaceWorkflowRunRequest,
    WorkspaceWorkflowRunResponse,
)
from app.services.artifacts.manifest import ArtifactManifestService
from app.services.message_lifecycle import cleanup_stale_streaming_messages
from app.services.queued_messages import get_active_agent_message
from app.services.stream_run_manager import stream_run_manager
from app.services.workspace.preview_verifier import (
    BrowserPreviewVerifier,
    BrowserPreviewVerifyDisabledError,
    BrowserPreviewVerifyError,
)
from app.services.workspace_deployment import (
    WorkspaceDeploymentDisabledError,
    WorkspaceDeploymentError,
    WorkspaceDeploymentNotFoundError,
    WorkspaceDeploymentService,
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
from app.services.workspace_workflow_runtime import (
    WorkflowRunNotFoundError,
    WorkflowRuntimeError,
    WorkspaceWorkflowRuntimeService,
)

router = APIRouter()
workspace_service = WorkspaceService()
artifact_manifest_service = ArtifactManifestService()
preview_service = WorkspacePreviewService(workspace_service)
browser_verifier = BrowserPreviewVerifier()
deployment_service = WorkspaceDeploymentService(workspace_service)
workflow_runtime_service = WorkspaceWorkflowRuntimeService(workspace_service)
ONE_CLICK_CONTAINER_AUTOMATION_KIND = "one_click_container_deploy"
ONE_CLICK_CONTAINER_PROMPT = "\n".join(
    [
        "请为当前 workspace 执行一键容器化部署。",
        "",
        "目标：即使当前没有 Dockerfile，也要先补齐可部署的静态站点容器文件，",
        "然后通过 AgentHub 平台部署工具发布。",
        "",
        "执行要求：",
        "1. 检查 workspace。若缺少 Dockerfile，请创建 Dockerfile 和",
        "   agenthub_container_server.py。",
        "   若 agenthub_container_server.py 已存在，先复用它，",
        "   只在 deployment build/run/health 失败后修复。",
        "2. 优先按静态站点处理：保留现有 index.html / CSS / JS / assets，",
        "   不要删除用户产物。",
        "3. agenthub_container_server.py 使用 Python 标准库启动 HTTP 服务，",
        "   监听 0.0.0.0:8000；/health 必须返回 200 和 ok；",
        "   其余路径服务 workspace 静态文件。",
        "4. Dockerfile 使用 python:3.12-slim，WORKDIR /app，COPY . .，",
        "   EXPOSE 8000，CMD 启动 agenthub_container_server.py。",
        "5. 创建文件后调用平台工具 create_deployment(kind=\"container\",",
        "   container_port=8000, health_path=\"/health\")。",
        "6. 如果容器 build/run/health 失败，按现有 deployment health repair loop",
        "   反思、修复 Dockerfile 或 server，再重新调用 create_deployment，",
        "   直到 published 或修复预算耗尽。",
        "7. 不要手动运行 docker、podman、npm dev server 或本地长驻服务；",
        "   部署必须由 AgentHub platform tool 完成。",
        "",
        "最终回复只给用户可读部署结果，不暴露内部 prompt、stderr、tool call id",
        "或 ReAct trace。",
    ]
)


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


def _map_deployment_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceDeploymentDisabledError):
        return _error(
            status.HTTP_403_FORBIDDEN,
            "workspace_deployment_disabled",
            str(exc),
        )
    if isinstance(exc, WorkspaceDeploymentNotFoundError):
        return _error(
            status.HTTP_404_NOT_FOUND,
            "workspace_deployment_not_found",
            str(exc),
        )
    if isinstance(exc, WorkspaceDeploymentError):
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "workspace_deployment_failed",
            str(exc),
        )
    return _map_preview_error(exc)


def _map_workflow_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkflowRunNotFoundError):
        return _error(
            status.HTTP_404_NOT_FOUND,
            "workflow_run_not_found",
            str(exc),
        )
    if isinstance(exc, WorkflowRuntimeError):
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "workflow_runtime_failed",
            str(exc),
        )
    return _map_workspace_error(exc)


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


@router.get(
    "/{conversation_id}/artifacts",
    response_model=WorkspaceArtifactListResponse,
)
async def list_workspace_artifacts(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceArtifactListResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    workspace = await workspace_service.get_or_create(db, conversation_id)
    entries = artifact_manifest_service.list_entries(Path(workspace.root_path))
    return WorkspaceArtifactListResponse(
        items=[WorkspaceArtifactResponse.model_validate(entry) for entry in entries]
    )


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
            viewports=[str(item) for item in payload.viewports],
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


@router.post(
    "/{conversation_id}/deployments",
    response_model=WorkspaceDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_deployment(
    conversation_id: UUID,
    payload: WorkspaceDeploymentRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceDeploymentResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    try:
        deployment = await deployment_service.create(
            db,
            conversation_id,
            kind=payload.kind,
            entry_path=payload.entry_path,
            requested_port=payload.requested_port,
            container_port=payload.container_port,
            health_path=payload.health_path,
            start_command=payload.start_command,
        )
        if payload.kind == "container" and deployment.status == "queued":
            await db.commit()
    except (
        WorkspaceDeploymentDisabledError,
        WorkspaceDeploymentError,
        WorkspaceViolation,
        WorkspaceFileNotFound,
        WorkspaceFileTooLarge,
        WorkspacePreviewDisabledError,
        WorkspacePreviewStartError,
    ) as exc:
        raise _map_deployment_error(exc) from exc
    return WorkspaceDeploymentResponse.model_validate(deployment)


@router.post(
    "/{conversation_id}/deployments/one-click-container",
    response_model=WorkspaceOneClickContainerDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_one_click_container_deployment(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceOneClickContainerDeploymentResponse:
    conversation = await _get_owned_conversation_or_404(db, user.id, conversation_id)
    workspace = await workspace_service.get_or_create(db, conversation_id)
    dockerfile_path = Path(workspace.root_path) / "Dockerfile"
    container_server_path = Path(workspace.root_path) / "agenthub_container_server.py"

    if dockerfile_path.is_file():
        try:
            deployment = await deployment_service.create(
                db,
                conversation_id,
                kind="container",
                container_port=8000,
                health_path="/health",
            )
            if deployment.status == "queued":
                await db.commit()
        except (
            WorkspaceDeploymentDisabledError,
            WorkspaceDeploymentError,
            WorkspaceViolation,
            WorkspaceFileNotFound,
            WorkspaceFileTooLarge,
            WorkspacePreviewDisabledError,
            WorkspacePreviewStartError,
        ) as exc:
            raise _map_deployment_error(exc) from exc
        return WorkspaceOneClickContainerDeploymentResponse(
            mode="direct",
            deployment=WorkspaceDeploymentResponse.model_validate(deployment),
        )

    await cleanup_stale_streaming_messages(db)
    active_message = await get_active_agent_message(db, conversation_id)
    if active_message is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "CONVERSATION_BUSY",
            "Conversation already has an active agent response.",
        )

    turn_options = {
        "requirement_alignment": "off",
        "ui_hidden": True,
        "automation_kind": ONE_CLICK_CONTAINER_AUTOMATION_KIND,
        "one_click_existing_container_server": container_server_path.is_file(),
    }
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=[{"type": "text", "text": ONE_CLICK_CONTAINER_PROMPT}],
        status="done",
        turn_options=turn_options,
    )
    db.add(user_message)
    await db.flush()

    agent_message = Message(
        conversation_id=conversation_id,
        role="agent",
        agent_id=ORCHESTRATOR_AGENT_ID,
        content=[],
        reply_to_id=user_message.id,
        status="streaming",
        turn_options=turn_options,
    )
    db.add(agent_message)
    conversation.last_message_at = datetime.now(UTC)
    await db.flush()
    await db.commit()

    await stream_run_manager.start(agent_message, _run_stream_session)
    return WorkspaceOneClickContainerDeploymentResponse(
        mode="orchestrator_prepare",
        automation_message_id=agent_message.id,
    )


@router.get(
    "/{conversation_id}/deployments",
    response_model=WorkspaceDeploymentListResponse,
)
async def list_workspace_deployments(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceDeploymentListResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    deployments = await deployment_service.list(db, conversation_id)
    return WorkspaceDeploymentListResponse(
        items=[WorkspaceDeploymentResponse.model_validate(item) for item in deployments]
    )


@router.get(
    "/{conversation_id}/deployments/{deployment_id}",
    response_model=WorkspaceDeploymentResponse,
)
async def get_workspace_deployment(
    conversation_id: UUID,
    deployment_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceDeploymentResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    deployment = await deployment_service.get(db, conversation_id, deployment_id)
    if deployment is None:
        raise _map_deployment_error(
            WorkspaceDeploymentNotFoundError("workspace deployment not found")
        )
    return WorkspaceDeploymentResponse.model_validate(deployment)


@router.delete(
    "/{conversation_id}/deployments/{deployment_id}",
    response_model=WorkspaceDeploymentResponse,
)
async def stop_workspace_deployment(
    conversation_id: UUID,
    deployment_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceDeploymentResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    deployment = await deployment_service.stop(db, conversation_id, deployment_id)
    if deployment is None:
        raise _map_deployment_error(
            WorkspaceDeploymentNotFoundError("workspace deployment not found")
        )
    return WorkspaceDeploymentResponse.model_validate(deployment)


@router.post(
    "/{conversation_id}/deployments/{deployment_id}/retry",
    response_model=WorkspaceDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def retry_workspace_deployment(
    conversation_id: UUID,
    deployment_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceDeploymentResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    try:
        deployment = await deployment_service.retry(db, conversation_id, deployment_id)
        if deployment is None:
            raise WorkspaceDeploymentNotFoundError("workspace deployment not found")
        if deployment.kind == "container" and deployment.status == "queued":
            await db.commit()
    except (
        WorkspaceDeploymentDisabledError,
        WorkspaceDeploymentError,
        WorkspaceDeploymentNotFoundError,
        WorkspaceViolation,
        WorkspaceFileNotFound,
        WorkspaceFileTooLarge,
        WorkspacePreviewDisabledError,
        WorkspacePreviewStartError,
    ) as exc:
        raise _map_deployment_error(exc) from exc
    return WorkspaceDeploymentResponse.model_validate(deployment)


@router.get("/{conversation_id}/deployments/{deployment_id}/download")
async def download_workspace_deployment(
    conversation_id: UUID,
    deployment_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    deployment = await deployment_service.get(db, conversation_id, deployment_id)
    if deployment is None or deployment.kind != "source_zip":
        raise _map_deployment_error(
            WorkspaceDeploymentNotFoundError("workspace source export not found")
        )
    if deployment.expires_at is not None and deployment.expires_at <= datetime.now(UTC):
        await deployment_service.stop(db, conversation_id, deployment_id)
        raise _map_deployment_error(
            WorkspaceDeploymentNotFoundError("workspace source export expired")
        )
    path = deployment_service.export_path(conversation_id, deployment_id)
    if deployment.status != "published" or not path.is_file():
        raise _map_deployment_error(
            WorkspaceDeploymentNotFoundError("workspace source export file not found")
        )
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"agenthub-workspace-{conversation_id}.zip",
    )


@router.post(
    "/{conversation_id}/workflow-runs",
    response_model=WorkspaceWorkflowRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_workflow_run(
    conversation_id: UUID,
    payload: WorkspaceWorkflowRunRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceWorkflowRunResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    try:
        run = await workflow_runtime_service.dry_run(
            db,
            conversation_id,
            path=payload.path,
            inputs=payload.inputs,
        )
    except (
        WorkflowRuntimeError,
        WorkspaceViolation,
        WorkspaceFileNotFound,
        WorkspaceFileTooLarge,
    ) as exc:
        raise _map_workflow_error(exc) from exc
    return WorkspaceWorkflowRunResponse.model_validate(run)


@router.get(
    "/{conversation_id}/workflow-runs",
    response_model=WorkspaceWorkflowRunListResponse,
)
async def list_workspace_workflow_runs(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    path: str | None = Query(default=None, min_length=1, max_length=512),
    limit: int = Query(default=20, ge=1, le=100),
) -> WorkspaceWorkflowRunListResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    runs = await workflow_runtime_service.list_runs(
        db,
        conversation_id,
        path=path,
        limit=limit,
    )
    return WorkspaceWorkflowRunListResponse(
        items=[WorkspaceWorkflowRunResponse.model_validate(run) for run in runs]
    )


@router.get(
    "/{conversation_id}/workflow-runs/{run_id}",
    response_model=WorkspaceWorkflowRunResponse,
)
async def get_workspace_workflow_run(
    conversation_id: UUID,
    run_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceWorkflowRunResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    try:
        run = await workflow_runtime_service.get_run(db, conversation_id, run_id)
    except WorkflowRunNotFoundError as exc:
        raise _map_workflow_error(exc) from exc
    return WorkspaceWorkflowRunResponse.model_validate(run)


@router.get(
    "/{conversation_id}/workflow-health",
    response_model=WorkspaceWorkflowHealthResponse,
)
async def get_workspace_workflow_health(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    path: str = Query(min_length=1, max_length=512),
) -> WorkspaceWorkflowHealthResponse:
    await _get_owned_conversation_or_404(db, user.id, conversation_id)
    validation_status, runtime_status, dry_run_status, health_status, latest = (
        await workflow_runtime_service.health(db, conversation_id, path=path)
    )
    return WorkspaceWorkflowHealthResponse(
        path=path,
        validation_status=validation_status,
        runtime_status=runtime_status,
        dry_run_status=dry_run_status,
        health_status=health_status,
        latest_run=(
            WorkspaceWorkflowRunResponse.model_validate(latest)
            if latest is not None
            else None
        ),
    )


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
