"""Run a direct deployed-backend E2E for preview and release hardening."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import httpx

BASE_URL = os.getenv("AGENTHUB_DEPLOYMENT_E2E_BASE_URL", "http://111.229.151.159:8000")
USERNAME = os.getenv("AGENTHUB_E2E_USERNAME", "12345678")
PASSWORD = os.getenv("AGENTHUB_E2E_PASSWORD", "12345678")
EXPECT_CONTAINER = os.getenv("AGENTHUB_E2E_EXPECT_CONTAINER", "true").lower() in {
    "1",
    "true",
    "yes",
}
CONTAINER_BASE_IMAGE = os.getenv("AGENTHUB_E2E_CONTAINER_BASE_IMAGE", "python:3.12-slim")
REPORT_PATH = Path(
    os.getenv(
        "AGENTHUB_DEPLOYMENT_E2E_REPORT_PATH",
        "/tmp/agenthub_deployment_release_api_e2e_report.json",  # noqa: S108
    )
)
EXCLUDED_PARTS = {
    ".agenthub",
    ".env",
    ".git",
    ".ssh",
    ".venv",
    "__pycache__",
    "node_modules",
    "secrets",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def assert_status(response: httpx.Response, expected: int) -> None:
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}, expected {expected}: {response.text}"
        )


def put_file(
    client: httpx.Client,
    headers: dict[str, str],
    conversation_id: str,
    path: str,
    content: str,
) -> None:
    response = client.put(
        f"/api/v1/workspaces/{conversation_id}/files/{path}",
        headers=headers,
        content=content.encode(),
    )
    assert_status(response, 204)


def create_deployment(
    client: httpx.Client,
    headers: dict[str, str],
    conversation_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json=payload,
    )
    assert_status(response, 201)
    return cast(dict[str, Any], response.json())


def contains_excluded_path(path: str) -> bool:
    return any(part in EXCLUDED_PARTS or part.startswith(".env.") for part in Path(path).parts)


def is_unavailable(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> bool:
    try:
        return client.get(url, headers=headers).status_code in {404, 410}
    except httpx.HTTPError:
        return True


def main() -> None:
    """Execute the direct API flow and always persist a report."""
    report: dict[str, Any] = {
        "passed": False,
        "started_at": utc_now(),
        "base_url": BASE_URL,
        "bugs": [],
        "warnings": [],
        "cleanup_checks": {},
    }
    conversation_id: str | None = None
    headers: dict[str, str] = {}
    client = httpx.Client(
        base_url=BASE_URL,
        timeout=90 if EXPECT_CONTAINER else 20,
        trust_env=False,
    )
    try:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
        )
        assert_status(login, 200)
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        agents = client.get("/api/v1/agents", headers=headers)
        assert_status(agents, 200)
        agent_ids = {item["id"] for item in agents.json()["items"]}
        if "orchestrator" not in agent_ids:
            raise AssertionError("builtin orchestrator agent is missing")

        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json={
                "title": f"Deployment Release API E2E {utc_now()}",
                "mode": "single",
                "agent_ids": ["orchestrator"],
            },
        )
        assert_status(conversation, 201)
        conversation_id = conversation.json()["id"]
        report["conversation_id"] = conversation_id

        put_file(
            client,
            headers,
            conversation_id,
            "index.html",
            (
                "<!doctype html><html><head><link rel='stylesheet' "
                "href='assets/styles.css'></head><body><h1>release-v1</h1>"
                "<script src='app.js'></script></body></html>"
            ),
        )
        put_file(client, headers, conversation_id, "assets/styles.css", "body{color:#123456}")
        put_file(client, headers, conversation_id, "app.js", "window.releaseReady = true;")
        put_file(
            client,
            headers,
            conversation_id,
            "server.py",
            (
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        if self.path == '/health':\n"
                "            self.send_response(200)\n"
                "            self.end_headers()\n"
                "            self.wfile.write(b'ok')\n"
                "        else:\n"
                "            self.send_response(200)\n"
                "            self.end_headers()\n"
                "            self.wfile.write(b'AgentHub container deployment')\n"
                "HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()\n"
            ),
        )
        put_file(
            client,
            headers,
            conversation_id,
            "Dockerfile",
            (
                f"FROM {CONTAINER_BASE_IMAGE}\n"
                "ENV PYTHONDONTWRITEBYTECODE=1\n"
                "WORKDIR /app\n"
                "COPY server.py .\n"
                "EXPOSE 8000\n"
                "CMD [\"python\", \"server.py\"]\n"
            ),
        )

        preview = client.post(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
            json={"entry_path": "index.html", "requested_port": 8082},
        )
        assert_status(preview, 201)
        preview_body = preview.json()
        preview_url = preview_body["url"]
        report["preview_url"] = preview_url
        preview_index = client.get(preview_url)
        assert_status(preview_index, 200)
        assert "release-v1" in preview_index.text
        assert preview_index.headers["x-content-type-options"] == "nosniff"
        assert "content-security-policy" in preview_index.headers
        parsed_preview = urlparse(preview_url)
        preview_origin = f"{parsed_preview.scheme}://{parsed_preview.netloc}"
        assert_status(client.get(f"{preview_origin}/assets/styles.css"), 200)
        assert_status(client.get(f"{preview_origin}/assets/"), 404)
        assert_status(
            client.get(f"{preview_origin}/.agenthub/manifest.json"),
            404,
        )

        static_release = create_deployment(
            client,
            headers,
            conversation_id,
            {"kind": "static_site", "entry_path": "index.html", "requested_port": 8082},
        )
        release_url = static_release["url"]
        report["release_url"] = release_url
        report["release_metadata"] = {
            key: static_release.get(key)
            for key in ("artifact_digest", "file_count", "size_bytes", "published_at")
        }
        assert "/releases/" in release_url
        released_v1 = client.get(release_url)
        assert_status(released_v1, 200)
        assert "release-v1" in released_v1.text

        put_file(
            client,
            headers,
            conversation_id,
            "index.html",
            "<!doctype html><html><body><h1>release-v2</h1></body></html>",
        )
        immutable = client.get(release_url)
        assert_status(immutable, 200)
        report["release_immutable"] = (
            "release-v1" in immutable.text and "release-v2" not in immutable.text
        )
        if not report["release_immutable"]:
            raise AssertionError("static release changed after workspace mutation")

        source_zip = create_deployment(client, headers, conversation_id, {"kind": "source_zip"})
        source_download = client.get(source_zip["download_url"], headers=headers)
        assert_status(source_download, 200)
        with zipfile.ZipFile(BytesIO(source_download.content)) as archive:
            zip_entries = sorted(archive.namelist())
        report["source_zip_entries"] = zip_entries
        report["source_zip_metadata"] = {
            key: source_zip.get(key)
            for key in ("artifact_digest", "file_count", "size_bytes", "expires_at")
        }
        if any(contains_excluded_path(entry) for entry in zip_entries):
            raise AssertionError("source zip contains an excluded path")

        container = create_deployment(
            client,
            headers,
            conversation_id,
            {"kind": "container", "container_port": 8000, "health_path": "/health"},
        )
        report["container_status"] = container["status"]
        report["container_deployment"] = {
            key: container.get(key)
            for key in (
                "id",
                "status",
                "url",
                "healthcheck_url",
                "host_port",
                "container_port",
                "runtime_kind",
                "runtime_status",
                "error",
            )
        }
        if container["status"] == "published":
            health = client.get(container["healthcheck_url"])
            assert_status(health, 200)
            if "ok" not in health.text.lower():
                raise AssertionError("container health endpoint did not return ok")
            stopped_container = client.delete(
                f"/api/v1/workspaces/{conversation_id}/deployments/{container['id']}",
                headers=headers,
            )
            assert_status(stopped_container, 200)
            report["container_stopped"] = True
            report["container_unavailable_after_stop"] = is_unavailable(client, container["url"])
        elif container["status"] == "not_supported":
            report["warnings"].append(
                {
                    "type": "container_disabled",
                    "message": "container worker is disabled on this backend",
                }
            )
            if EXPECT_CONTAINER:
                raise AssertionError("expected published container deployment, got not_supported")
        else:
            raise AssertionError(f"container deployment failed: {container}")

        stopped = client.delete(
            f"/api/v1/workspaces/{conversation_id}/deployments/{static_release['id']}",
            headers=headers,
        )
        assert_status(stopped, 200)
        invalidated = client.get(release_url)
        report["release_stopped"] = invalidated.status_code in {404, 410}
        if not report["release_stopped"]:
            raise AssertionError("stopped release token remains accessible")

        deleted = client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
        assert_status(deleted, 204)
        conversation_id = None
        report["cleanup_checks"] = {
            "preview_unavailable": is_unavailable(client, preview_url),
            "release_unavailable": is_unavailable(client, release_url),
            "source_zip_unavailable": is_unavailable(
                client,
                source_zip["download_url"],
                headers=headers,
            ),
        }
        if not all(report["cleanup_checks"].values()):
            raise AssertionError("conversation cleanup left generated resources accessible")
        report["passed"] = True
    except Exception as exc:  # noqa: BLE001
        report["bugs"].append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        if conversation_id and headers:
            cleanup = client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
            report["cleanup_status_code"] = cleanup.status_code
        client.close()
        report["finished_at"] = utc_now()
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
