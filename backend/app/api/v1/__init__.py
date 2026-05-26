"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    auth,
    context_compression,
    conversations,
    messages,
    stream,
    workspaces,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(
    context_compression.router,
    prefix="/context-compression",
    tags=["Context Compression"],
)
api_router.include_router(messages.router, tags=["Messages"])
api_router.include_router(stream.router, tags=["Messages"])
api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["Workspaces"])
