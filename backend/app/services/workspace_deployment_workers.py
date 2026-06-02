"""Shared deployment worker protocol."""

from __future__ import annotations

from typing import Protocol


class DeploymentWorker(Protocol):
    """Marker protocol for platform-owned deployment workers."""
