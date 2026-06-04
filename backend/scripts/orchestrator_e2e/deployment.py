"""Deployment polling and source package checks."""

from __future__ import annotations

import time
import zipfile
from io import BytesIO
from typing import Any

import httpx

CONTAINER_TERMINAL_STATUSES = {"published", "failed", "stopped", "not_supported"}
SOURCE_EXPORT_EXCLUDED_PARTS = {
    ".agenthub",
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".env",
    ".ssh",
    "secrets",
}


def get_deployment_detail(
    client: httpx.Client,
    conversation_id: str,
    headers: dict[str, str],
    deployment_id: str,
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/workspaces/{conversation_id}/deployments/{deployment_id}",
        headers=headers,
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def wait_for_deployment_terminal(
    client: httpx.Client,
    conversation_id: str,
    headers: dict[str, str],
    deployment: dict[str, Any],
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> tuple[dict[str, Any], float]:
    deployment_id = deployment.get("id")
    if not isinstance(deployment_id, str) or not deployment_id:
        return deployment, 0.0
    started = time.monotonic()
    current = deployment
    while current.get("status") not in CONTAINER_TERMINAL_STATUSES:
        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            return current, elapsed
        time.sleep(interval_seconds)
        current = get_deployment_detail(client, conversation_id, headers, deployment_id)
    return current, time.monotonic() - started


def source_zip_entries(content: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.namelist()


def source_zip_excludes_sensitive_paths(entries: list[str]) -> bool:
    return all(
        not SOURCE_EXPORT_EXCLUDED_PARTS.intersection(entry.split("/"))
        for entry in entries
    )

