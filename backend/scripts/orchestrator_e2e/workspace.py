"""Workspace tree, file, artifact, and workflow API helpers."""

from __future__ import annotations

from typing import Any

import httpx


def flatten_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
    if node.get("type") == "file":
        return [node]
    files: list[dict[str, Any]] = []
    for child in node.get("children") or []:
        files.extend(flatten_tree(child))
    return files


def file_by_basename(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in files:
        name = str(item.get("path", "")).rsplit("/", 1)[-1]
        if name and name not in result:
            result[name] = item
    return result


def read_workspace_file(
    client: httpx.Client,
    conversation_id: str,
    headers: dict[str, str],
    path: str,
) -> str:
    response = client.get(
        f"/api/v1/workspaces/{conversation_id}/files/{path}",
        headers=headers,
    )
    response.raise_for_status()
    return response.text


def get_workspace_artifacts(
    client: httpx.Client,
    conversation_id: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/v1/workspaces/{conversation_id}/artifacts",
        headers=headers,
    )
    response.raise_for_status()
    items = response.json().get("items")
    return items if isinstance(items, list) else []


def put_workspace_file(
    client: httpx.Client,
    conversation_id: str,
    headers: dict[str, str],
    path: str,
    content: str,
) -> None:
    response = client.put(
        f"/api/v1/workspaces/{conversation_id}/files/{path}",
        headers=headers,
        content=content.encode(),
    )
    response.raise_for_status()

