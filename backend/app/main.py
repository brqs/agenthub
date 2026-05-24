"""FastAPI application entry."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    # TODO: warmup connections, prewarm caches, etc.
    yield


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
