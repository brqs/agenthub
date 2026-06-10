"""Public AgentHub server capability metadata."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ServerFeatures(BaseModel):
    uploads: bool
    workspace: bool
    orchestrator: bool
    desktop_local_stack: bool


class ServerAuthInfo(BaseModel):
    type: Literal["jwt"] = "jwt"


class ServerLimits(BaseModel):
    max_upload_mb: int


class ServerInfoResponse(BaseModel):
    server_id: str
    version: str
    deployment_mode: Literal["local", "hosted"]
    features: ServerFeatures
    auth: ServerAuthInfo
    limits: ServerLimits
