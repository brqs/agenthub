"""Public server identity and capability endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.server_info import (
    ServerAuthInfo,
    ServerFeatures,
    ServerInfoResponse,
    ServerLimits,
)

router = APIRouter()


@router.get("/server-info", response_model=ServerInfoResponse)
async def get_server_info() -> ServerInfoResponse:
    """Return non-sensitive metadata used by multi-backend clients."""
    from app.main import app

    return ServerInfoResponse(
        server_id=settings.agenthub_server_id,
        version=app.version,
        deployment_mode=settings.agenthub_deployment_mode,
        features=ServerFeatures(
            uploads=True,
            workspace=True,
            orchestrator=True,
            desktop_local_stack=settings.agenthub_deployment_mode == "local",
        ),
        auth=ServerAuthInfo(),
        limits=ServerLimits(max_upload_mb=settings.upload_max_file_bytes // 1_000_000),
    )
