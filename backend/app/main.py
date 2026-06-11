"""FastAPI application entry."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.releases import router as releases_router
from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import SessionFactory
from app.services.builtin_agent_config import reconcile_builtin_agents
from app.services.workspace.janitor import WorkspaceResourceJanitor

logger = logging.getLogger("uvicorn.error")


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    dependencies: dict[str, str]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    _ = app
    logger.info("startup.stage=builtin_agents status=starting")
    await _upgrade_builtin_agent_configs()
    logger.info("startup.stage=builtin_agents status=complete")
    janitor = WorkspaceResourceJanitor()
    logger.info("startup.stage=workspace_cleanup status=starting")
    await janitor.cleanup_once()
    logger.info("startup.stage=workspace_cleanup status=complete")
    task = asyncio.create_task(janitor.run_forever())
    try:
        logger.info("startup.stage=application status=ready")
        yield
    finally:
        logger.info("shutdown.stage=workspace_cleanup status=stopping")
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("shutdown.stage=application status=complete")


async def _upgrade_builtin_agent_configs() -> None:
    try:
        async with SessionFactory() as db:
            changed = await reconcile_builtin_agents(db)
            if changed:
                await db.commit()
            logger.info(
                "startup.stage=builtin_agents status=reconciled changed=%s",
                changed,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to upgrade built-in agent configs: %s", exc)


app = FastAPI(
    title="AgentHub API",
    version="0.1.0",
    description="Multi-agent collaboration platform — IM-style chat interface.",
    lifespan=lifespan,
)

# ─── CORS ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Cache-Control",
        "Last-Event-ID",
    ],
)


# ─── Health ───
@app.get("/health", response_model=HealthResponse, tags=["Misc"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=app.version,
        environment=settings.environment,
        dependencies={
            "api": "ok",
            "database": "configured",
            "redis": "configured",
        },
    )


# ─── API v1 ───
app.include_router(api_router)
app.include_router(releases_router)
