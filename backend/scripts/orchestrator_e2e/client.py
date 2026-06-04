"""HTTP client helpers shared by live scenario runners."""

from __future__ import annotations

import os
from typing import Any

import httpx

from .config import E2ESettings


def auth_headers(
    client: httpx.Client,
    settings: E2ESettings,
    report: dict[str, Any],
    started_at: float,
) -> dict[str, str]:
    if settings.use_temporary_user:
        username = f"cap_v2_e2e_{int(started_at)}_{os.getpid()}"
        password = "P@ssw0rd!12345678"  # noqa: S105
        register = client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": password},
        )
        report["register_status_code"] = register.status_code
        if register.status_code == 201:
            report["account"] = username
            return {"Authorization": f"Bearer {register.json()['access_token']}"}
        report["register_error"] = register.text

    login = client.post(
        "/api/v1/auth/login",
        json={"username": settings.username, "password": settings.password},
    )
    report["login_status_code"] = login.status_code
    login.raise_for_status()
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def fetch_orchestrator_run_detail(
    client: httpx.Client,
    headers: dict[str, str],
    conversation_id: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    runs = client.get(
        f"/api/v1/conversations/{conversation_id}/orchestrator-runs",
        headers=headers,
    )
    report["orchestrator_runs_status_code"] = runs.status_code
    if runs.status_code != 200:
        report["orchestrator_runs_error"] = runs.text
        return {}
    items = runs.json().get("items", [])
    report["orchestrator_runs"] = items
    if not items or not isinstance(items[0].get("id"), str):
        return {}
    detail = client.get(
        f"/api/v1/conversations/{conversation_id}/orchestrator-runs/{items[0]['id']}",
        headers=headers,
    )
    report["orchestrator_run_detail_status_code"] = detail.status_code
    if detail.status_code != 200:
        report["orchestrator_run_detail_error"] = detail.text
        return {}
    body = detail.json()
    if isinstance(body, dict):
        report["orchestrator_run_detail"] = body
        return body
    return {}

