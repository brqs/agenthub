"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import agents, auth, conversations, messages, stream

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(messages.router, tags=["Messages"])
api_router.include_router(stream.router, tags=["Messages"])
api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
