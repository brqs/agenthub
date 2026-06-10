"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    auth,
    context_compression,
    conversations,
    events,
    local_runtime_connectors,
    memories,
    messages,
    server_info,
    shares,
    stream,
    uploads,
    workspaces,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(events.router, prefix="/events", tags=["Events"])
api_router.include_router(
    local_runtime_connectors.router,
    prefix="/local-runtime-connectors",
    tags=["Local Runtime Connectors"],
)
api_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(
    context_compression.router,
    prefix="/context-compression",
    tags=["Context Compression"],
)
api_router.include_router(messages.router, tags=["Messages"])
api_router.include_router(server_info.router, tags=["Misc"])
api_router.include_router(shares.router, tags=["Shares"])
api_router.include_router(stream.router, tags=["Messages"])
api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["Uploads"])
api_router.include_router(memories.router, prefix="/memories", tags=["Memories"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["Workspaces"])
