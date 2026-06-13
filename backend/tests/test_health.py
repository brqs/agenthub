"""Smoke test for /health endpoint."""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app import main as main_module
from app.core.config import Settings, settings
from app.main import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["environment"]
    assert body["dependencies"]["api"] == "ok"


@pytest.mark.asyncio
async def test_server_info_exposes_public_capabilities() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/server-info")

    assert resp.status_code == 200
    body = resp.json()
    assert body["server_id"] == settings.agenthub_server_id
    assert body["version"] == "0.1.0"
    assert body["deployment_mode"] in {"local", "hosted"}
    assert body["features"]["uploads"] is True
    assert body["features"]["workspace"] is True
    assert body["auth"]["type"] == "jwt"
    assert body["limits"]["max_upload_mb"] == settings.upload_max_file_bytes // 1_000_000


def test_default_cors_allows_tauri_origin() -> None:
    assert "http://tauri.localhost" in settings.cors_origin_list
    assert "https://tauri.localhost" in settings.cors_origin_list


def test_default_agent_stream_timeouts_support_repair_loops() -> None:
    local_settings = Settings()

    assert local_settings.agent_stream_idle_timeout_seconds == 900
    assert local_settings.agent_stream_hard_timeout_seconds == 3600


def test_desktop_cors_is_appended_when_cors_origins_are_overridden() -> None:
    local_settings = Settings(cors_origins="http://localhost:5173")

    assert local_settings.cors_origin_list == [
        "http://localhost:5173",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ]


@pytest.mark.asyncio
async def test_cors_preflight_allows_desktop_cache_control_header() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/api/v1/server-info",
            headers={
                "Origin": "http://tauri.localhost",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": (
                    "authorization,accept,cache-control,last-event-id"
                ),
            },
        )

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://tauri.localhost"
    allowed_headers = resp.headers["access-control-allow-headers"].lower()
    assert "cache-control" in allowed_headers
    assert "last-event-id" in allowed_headers


@pytest.mark.asyncio
async def test_lifespan_emits_structured_startup_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeJanitor:
        async def cleanup_once(self) -> None:
            return None

        async def run_forever(self) -> None:
            await __import__("asyncio").sleep(3600)

    async def fake_upgrade() -> None:
        return None

    monkeypatch.setattr(main_module, "WorkspaceResourceJanitor", FakeJanitor)
    monkeypatch.setattr(main_module, "_upgrade_builtin_agent_configs", fake_upgrade)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    async with main_module.lifespan(app):
        pass

    messages = [record.getMessage() for record in caplog.records]
    assert "startup.stage=builtin_agents status=starting" in messages
    assert "startup.stage=workspace_cleanup status=complete" in messages
    assert "startup.stage=application status=ready" in messages
    assert "shutdown.stage=application status=complete" in messages
