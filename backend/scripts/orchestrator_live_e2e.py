"""Run the deployed Orchestrator 8082 demo flow and write a JSON report.

This script intentionally uses the same HTTP API surface as the deployed frontend.
It is opt-in and intended for manual/live verification, not default CI.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BASE_URL = os.getenv("AGENTHUB_E2E_BASE_URL", "http://154.44.25.94:1573")
USERNAME = os.getenv("AGENTHUB_E2E_USERNAME", "12345678")
PASSWORD = os.getenv("AGENTHUB_E2E_PASSWORD", "12345678")
SSE_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_SSE_PATH",
        "/tmp/agenthub_orchestrator_8082_sse.jsonl",  # noqa: S108 - documented output.
    )
)
REPORT_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_REPORT_PATH",
        "/tmp/agenthub_orchestrator_8082_report.json",  # noqa: S108 - documented output.
    )
)
PROMPT = os.getenv(
    "AGENTHUB_E2E_PROMPT",
    "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff 和网页预览的前端"
    "开发演示，主题随机，部署在端口8082",
)
AGENT_IDS = ["orchestrator", "claude-code", "opencode-helper", "codex-helper"]
REQUIRED_FRONTEND_FILES = {"index.html", "styles.css", "app.js"}
SERVER_COMMAND_RE = re.compile(
    r"npm\s+run\s+dev|pnpm\s+dev|vite\s+--host|python\d*\s+-m\s+http\.server|"
    r"http-server|next\s+dev|npm\s+(?:run\s+)?start|node\s+server\.js|"
    r"app\.listen\s*\(|express\s+server|server\.js",
    re.I,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def parse_sse(response: httpx.Response, started_at: float) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_event = "message"
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal current_event, data_lines
        if current_event == "message" and not data_lines:
            return
        raw = "\n".join(data_lines)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"_raw": raw}
        event = {
            "ts": utc_now(),
            "elapsed_seconds": round(time.time() - started_at, 3),
            "event": current_event,
            "data": data,
        }
        events.append(event)
        append_jsonl(SSE_PATH, event)
        current_event = "message"
        data_lines = []

    for line in response.iter_lines():
        if line == "":
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
    flush()
    return events


def flatten_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
    if node.get("type") == "file":
        return [node]
    files: list[dict[str, Any]] = []
    for child in node.get("children") or []:
        files.extend(flatten_tree(child))
    return files


def first_html(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    html_files = [
        item
        for item in files
        if str(item.get("path", "")).lower().endswith((".html", ".htm"))
    ]
    if not html_files:
        return None
    for preferred in ("index.html", "demo.html", "orchestrator-demo.html"):
        for item in html_files:
            path = str(item.get("path", ""))
            if path == preferred or path.endswith(f"/{preferred}"):
                return item
    return max(html_files, key=lambda item: int(item.get("size") or 0))


def block_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        for key in ("text", "code", "url", "title", "description", "filename"):
            value = block.get(key)
            if isinstance(value, str):
                parts.append(value)
        if block.get("type") == "tool_call":
            parts.append(json.dumps(block.get("arguments") or {}, ensure_ascii=False))
            output = block.get("output_preview")
            if isinstance(output, str):
                parts.append(output)
    return "\n".join(parts)


def classify_tool_errors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    tool_names_by_call_id: dict[str, str] = {}
    for event in events:
        data = event.get("data") or {}
        if event.get("event") == "tool_call":
            call_id = data.get("call_id")
            tool_name = data.get("tool_name")
            if isinstance(call_id, str) and isinstance(tool_name, str):
                tool_names_by_call_id[call_id] = tool_name
            continue
        if event.get("event") != "tool_result":
            continue
        if data.get("tool_status") == "error":
            call_id = data.get("call_id")
            tool_name = tool_names_by_call_id.get(call_id) if isinstance(call_id, str) else None
            failures.append(
                {
                    "elapsed_seconds": event.get("elapsed_seconds"),
                    "data": data,
                    "tool_name": tool_name,
                    "recoverable": tool_name != "start_workspace_preview",
                }
            )
    return failures


def main() -> None:
    started_at = time.time()
    SSE_PATH.write_text("", encoding="utf-8")
    report: dict[str, Any] = {
        "started_at": utc_now(),
        "base_url": BASE_URL,
        "account": USERNAME,
        "prompt": PROMPT,
        "target_agent_ids": AGENT_IDS,
        "artifacts": {"sse_jsonl": str(SSE_PATH), "report_json": str(REPORT_PATH)},
        "checks": {},
        "bugs": [],
        "warnings": [],
    }

    timeout = httpx.Timeout(connect=20, read=None, write=20, pool=20)
    with httpx.Client(base_url=BASE_URL, timeout=timeout, follow_redirects=True) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
        )
        report["login_status_code"] = login.status_code
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        agents = client.get("/api/v1/agents", headers=headers)
        agents.raise_for_status()
        agent_items = agents.json().get("items", [])
        agent_ids = {item.get("id") for item in agent_items}
        missing_agents = [agent_id for agent_id in AGENT_IDS if agent_id not in agent_ids]
        report["checks"]["target_agents_present"] = not missing_agents
        if missing_agents:
            raise RuntimeError(f"missing target agents: {missing_agents}")

        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json={
                "title": f"Orchestrator Real Flow 8082 Demo {int(started_at)}",
                "mode": "group",
                "agent_ids": AGENT_IDS,
            },
        )
        conversation.raise_for_status()
        conv = conversation.json()
        conv_id = conv["id"]
        report["conversation"] = conv

        send = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=headers,
            json={
                "content": [{"type": "text", "text": PROMPT}],
                "target_agent_id": "orchestrator",
            },
        )
        send.raise_for_status()
        sent = send.json()
        agent_message_id = sent["agent_message"]["id"]
        report["user_message_id"] = sent["user_message"]["id"]
        report["agent_message_id"] = agent_message_id

        with client.stream(
            "GET",
            f"/api/v1/messages/{agent_message_id}/stream",
            headers=headers,
        ) as stream:
            report["stream_status_code"] = stream.status_code
            stream.raise_for_status()
            events = parse_sse(stream, started_at)
        report["stream_event_count"] = len(events)
        report["agent_switch_to_agents"] = [
            event["data"].get("to_agent")
            for event in events
            if event.get("event") == "agent_switch" and isinstance(event.get("data"), dict)
        ]

        messages = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
        messages.raise_for_status()
        items = messages.json().get("items", [])
        target = next((item for item in items if item.get("id") == agent_message_id), None)
        report["target_agent_message"] = target
        report["checks"]["message_done"] = bool(target and target.get("status") == "done")

        runs = client.get(f"/api/v1/conversations/{conv_id}/orchestrator-runs", headers=headers)
        if runs.status_code == 200:
            run_items = runs.json().get("items", [])
            report["orchestrator_runs"] = run_items
            if run_items:
                report["checks"]["planner_used_llm"] = (
                    run_items[0].get("plan_source") != "legacy template"
                )
                final_summary = "\n".join(
                    str(item.get("final_summary") or "") for item in run_items
                )
                report["checks"]["orchestrator_summary_no_missing_or_pending"] = (
                    "artifact_missing" not in final_summary
                    and "\n- pending:" not in final_summary
                )
                if not report["checks"]["orchestrator_summary_no_missing_or_pending"]:
                    report["bugs"].append(
                        {
                            "code": "orchestrator_summary_missing_or_pending",
                            "symptom": (
                                "Orchestrator run completed but final_summary still "
                                "reported artifact_missing or pending tasks."
                            ),
                            "reproduction": [
                                "Create the live group conversation.",
                                "Send the 8082 frontend demo prompt to @orchestrator.",
                                "Inspect GET /api/v1/conversations/{id}/orchestrator-runs.",
                            ],
                            "evidence": final_summary,
                        }
                    )

        tree = client.get(f"/api/v1/workspaces/{conv_id}/tree", headers=headers)
        tree.raise_for_status()
        report["workspace_tree"] = tree.json()
        files = flatten_tree(report["workspace_tree"]["tree"])
        report["workspace_files"] = files
        file_names = {str(item.get("path", "")).rsplit("/", 1)[-1] for item in files}
        missing_frontend_files = sorted(REQUIRED_FRONTEND_FILES - file_names)
        report["checks"]["workspace_has_required_frontend_files"] = (
            not missing_frontend_files
        )
        if missing_frontend_files:
            report["bugs"].append(
                {
                    "code": "missing_required_frontend_files",
                    "symptom": (
                        "Workspace did not contain the expected static frontend "
                        "filenames index.html, styles.css, and app.js."
                    ),
                    "missing": missing_frontend_files,
                    "workspace_files": [item.get("path") for item in files],
                }
            )
        entry = first_html(files)
        report["entry_html"] = entry
        report["checks"]["has_html_artifact"] = entry is not None

        html_text = ""
        if entry is not None:
            file_response = client.get(
                f"/api/v1/workspaces/{conv_id}/files/{entry['path']}",
                headers=headers,
            )
            file_response.raise_for_status()
            html_text = file_response.text
            report["checks"]["html_has_task_breakdown"] = bool(
                re.search(r"任务|拆解|task", html_text, re.I)
            )
            report["checks"]["html_has_code_artifact"] = bool(
                re.search(r"代码|code|artifact|产物", html_text, re.I)
            )
            report["checks"]["html_has_diff"] = bool(
                re.search(r"\bDiff\b|diff|---|\+\+\+|差异", html_text, re.I)
            )
            report["checks"]["html_has_preview"] = bool(
                re.search(r"预览|preview|iframe|viewport|网页", html_text, re.I)
            )
            if not all(
                report["checks"].get(key, False)
                for key in (
                    "html_has_task_breakdown",
                    "html_has_code_artifact",
                    "html_has_diff",
                    "html_has_preview",
                )
            ):
                report["bugs"].append(
                    {
                        "code": "artifact_missing_required_sections",
                        "symptom": (
                            "The entry HTML did not visibly cover all requested "
                            "demo sections: task breakdown, code artifacts, Diff, "
                            "and webpage preview."
                        ),
                        "checks": {
                            key: report["checks"].get(key, False)
                            for key in (
                                "html_has_task_breakdown",
                                "html_has_code_artifact",
                                "html_has_diff",
                                "html_has_preview",
                            )
                        },
                        "entry_html": entry["path"],
                    }
                )

            content_blocks = (target or {}).get("content") or []
            preview_tool_blocks = [
                block
                for block in content_blocks
                if block.get("type") == "tool_call"
                and block.get("tool_name") == "start_workspace_preview"
            ]
            preview_message_blocks = [
                block for block in content_blocks if block.get("type") == "web_preview"
            ]
            report["checks"]["platform_preview_tool_called"] = bool(preview_tool_blocks)
            report["checks"]["platform_preview_tool_succeeded"] = any(
                block.get("status") == "ok" for block in preview_tool_blocks
            )
            report["checks"]["preview_url_in_agent_message"] = bool(
                preview_message_blocks
                and isinstance(preview_message_blocks[0].get("url"), str)
                and preview_message_blocks[0]["url"].startswith("http")
            )

            preview = client.get(
                f"/api/v1/workspaces/{conv_id}/preview",
                headers=headers,
            )
            report["preview_get_status_code"] = preview.status_code
            if preview.status_code == 200:
                preview_body = preview.json()
                report["preview_8082"] = preview_body
                report["checks"]["preview_uses_requested_8082"] = (
                    preview_body.get("port") == 8082
                    and ":8082/" in str(preview_body.get("url", ""))
                )
                report["checks"]["platform_preview_auto_started"] = (
                    preview_body.get("entry_path") == entry["path"]
                    and preview_body.get("status") == "running"
                )
                public = httpx.get(preview_body["url"], timeout=10, trust_env=False)
                report["checks"]["preview_8082_public_accessible"] = (
                    public.status_code == 200
                )
            else:
                report["preview_8082_error"] = preview.text
                report["checks"]["preview_uses_requested_8082"] = False
                report["checks"]["platform_preview_auto_started"] = False
                report["checks"]["preview_8082_public_accessible"] = False
            if not all(
                report["checks"].get(key, False)
                for key in (
                    "platform_preview_tool_called",
                    "platform_preview_tool_succeeded",
                    "platform_preview_auto_started",
                    "preview_url_in_agent_message",
                )
            ):
                report["bugs"].append(
                    {
                        "code": "platform_preview_not_auto_started",
                        "symptom": (
                            "The user requested deployment/preview, but the agent stream "
                            "did not complete a platform start_workspace_preview tool call."
                        ),
                        "checks": {
                            key: report["checks"].get(key, False)
                            for key in (
                                "platform_preview_tool_called",
                                "platform_preview_tool_succeeded",
                                "platform_preview_auto_started",
                                "preview_url_in_agent_message",
                            )
                        },
                        "preview_get_status_code": preview.status_code,
                        "preview_error": report.get("preview_8082_error"),
                    }
                )

        text = block_text((target or {}).get("content") or [])
        report["checks"]["agent_output_no_long_running_server_command"] = (
            SERVER_COMMAND_RE.search(text) is None
        )
        report["checks"]["dispatch_only_group_members"] = all(
            agent_id in {"claude-code", "opencode-helper", "codex-helper"}
            for agent_id in report["agent_switch_to_agents"]
        )
        report["checks"]["no_raw_input_tool_arguments"] = '"_raw_input"' not in text
        report["checks"]["no_workspace_path_escape_error"] = "path escapes workspace" not in text

        tool_errors = classify_tool_errors(events)
        fatal_tool_errors = [error for error in tool_errors if not error.get("recoverable")]
        if fatal_tool_errors:
            report["bugs"].append(
                {
                    "code": "fatal_tool_result_errors",
                    "symptom": "A platform-critical tool_result returned error.",
                    "evidence": fatal_tool_errors,
                }
            )
        recoverable_tool_errors = [
            error for error in tool_errors if error.get("recoverable")
        ]
        report["recoverable_tool_result_errors"] = recoverable_tool_errors
        if recoverable_tool_errors:
            report["warnings"].append(
                {
                    "code": "recoverable_tool_result_errors",
                    "count": len(recoverable_tool_errors),
                    "evidence": recoverable_tool_errors,
                }
            )

        hard_checks = {
            "message_done": report["checks"].get("message_done", False),
            "planner_used_llm": report["checks"].get("planner_used_llm", False),
            "has_html_artifact": report["checks"].get("has_html_artifact", False),
            "workspace_has_required_frontend_files": report["checks"].get(
                "workspace_has_required_frontend_files",
                False,
            ),
            "artifact_covers_required_sections": all(
                report["checks"].get(key, False)
                for key in (
                    "html_has_task_breakdown",
                    "html_has_code_artifact",
                    "html_has_diff",
                    "html_has_preview",
                )
            ),
            "preview_8082_public_accessible": report["checks"].get(
                "preview_8082_public_accessible",
                False,
            ),
            "preview_uses_requested_8082": report["checks"].get(
                "preview_uses_requested_8082",
                False,
            ),
            "platform_preview_tool_called": report["checks"].get(
                "platform_preview_tool_called",
                False,
            ),
            "platform_preview_auto_started": report["checks"].get(
                "platform_preview_auto_started",
                False,
            ),
            "preview_url_in_agent_message": report["checks"].get(
                "preview_url_in_agent_message",
                False,
            ),
            "dispatch_only_group_members": report["checks"].get(
                "dispatch_only_group_members",
                False,
            ),
            "agent_output_no_long_running_server_command": report["checks"].get(
                "agent_output_no_long_running_server_command",
                False,
            ),
            "orchestrator_summary_no_missing_or_pending": report["checks"].get(
                "orchestrator_summary_no_missing_or_pending",
                False,
            ),
        }
        report["acceptance"] = {**hard_checks, "passed": all(hard_checks.values())}

    report["finished_at"] = utc_now()
    report["duration_seconds"] = round(time.time() - started_at, 3)
    write_json(REPORT_PATH, report)
    print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
    print(f"report={REPORT_PATH}")
    print(f"sse={SSE_PATH}")


if __name__ == "__main__":
    main()
