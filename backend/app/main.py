"""FastAPI application entry."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.releases import router as releases_router
from app.api.v1 import api_router
from app.core.config import settings
from app.services.workspace.janitor import WorkspaceResourceJanitor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    _ = app
    janitor = WorkspaceResourceJanitor()
    await janitor.cleanup_once()
    task = asyncio.create_task(janitor.run_forever())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


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
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# ─── Health ───
@app.get("/health", tags=["Misc"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ─── API v1 ───
app.include_router(api_router)
app.include_router(releases_router)
