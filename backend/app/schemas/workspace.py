"""Workspace API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceTreeNode(BaseModel):
    name: str
    path: str
    type: Literal["directory", "file"]
    children: list[WorkspaceTreeNode] = Field(default_factory=list)
    size: int | None = None
    mime_type: str | None = None


class WorkspaceTreeResponse(BaseModel):
    root: str
    tree: WorkspaceTreeNode
