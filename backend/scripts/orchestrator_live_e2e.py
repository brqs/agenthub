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
SCENARIO = os.getenv("AGENTHUB_E2E_SCENARIO", "quality").strip().lower()
FULLSTACK_SCENARIO = SCENARIO == "fullstack"
DEFAULT_FULLSTACK_SSE_PATH = "/tmp/agenthub_fullstack_flow_sse.jsonl"  # noqa: S108
DEFAULT_QUALITY_SSE_PATH = "/tmp/agenthub_orchestrator_quality_sse.jsonl"  # noqa: S108
DEFAULT_FULLSTACK_REPORT_PATH = "/tmp/agenthub_fullstack_flow_report.json"  # noqa: S108
DEFAULT_QUALITY_REPORT_PATH = "/tmp/agenthub_orchestrator_quality_report.json"  # noqa: S108
DEFAULT_FULLSTACK_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_fullstack_flow_browser.json"  # noqa: S108
)
DEFAULT_QUALITY_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_quality_browser.json"  # noqa: S108
)
SSE_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_SSE_PATH",
        DEFAULT_FULLSTACK_SSE_PATH if FULLSTACK_SCENARIO else DEFAULT_QUALITY_SSE_PATH,
    )
)
REPORT_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_REPORT_PATH",
        (
            DEFAULT_FULLSTACK_REPORT_PATH
            if FULLSTACK_SCENARIO
            else DEFAULT_QUALITY_REPORT_PATH
        ),
    )
)
BROWSER_REPORT_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_BROWSER_REPORT_PATH",
        (
            DEFAULT_FULLSTACK_BROWSER_REPORT_PATH
            if FULLSTACK_SCENARIO
            else DEFAULT_QUALITY_BROWSER_REPORT_PATH
        ),
    )
)
FULLSTACK_PROMPT = "\n".join(
    (
        "@orchestrator 请完成一个前后端产品交付演示，主题是“团队 OKR 轻量看板”。",
        "",
        "流程要求：",
        "1. 先产出 planning.md，包含产品目标、页面结构、后端 API、数据模型、"
        "前后端分工、验收标准。",
        "2. 然后并行调度 claude-code 和 opencode-helper：",
        "   - claude-code 按 planning.md 实现前端，生成 index.html、styles.css、"
        "app.js。",
        "   - opencode-helper 按 planning.md 实现后端代码产物，生成 "
        "backend_app.py、api.md、backend_tests.md。",
        "   两个任务互不依赖，必须并行执行。",
        "3. 等前端和后端产物都完成后，调度 codex-helper 进行审阅测试，生成 "
        "review.md，检查前后端接口一致性、文件完整性、代码风险、测试建议。",
        "4. 最后由 orchestrator 调用平台 preview tool，把前端上线到端口8082，"
        "并完成浏览器级质量验收。",
        "5. 最终总结必须列出任务拆解、并行执行情况、代码产物、Diff/变更摘要、"
        "测试审阅结果、8082 预览 URL 和已知限制。",
        "",
        "当前平台不要求启动后端长驻服务；后端交付以 workspace 代码产物、"
        "API 文档和测试说明为准。",
    )
)
PROMPT = os.getenv(
    "AGENTHUB_E2E_PROMPT",
    FULLSTACK_PROMPT
    if FULLSTACK_SCENARIO
    else (
        "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff、网页预览、"
        "按钮交互和移动端适配的前端开发演示，主题随机，部署在端口8082，"
        "并完成浏览器级质量验收"
    ),
)
AGENT_IDS = ["orchestrator", "claude-code", "opencode-helper", "codex-helper"]
REQUIRED_FRONTEND_FILES = {"index.html", "styles.css", "app.js"}
REQUIRED_FULLSTACK_FILES = {
    "planning.md",
    "index.html",
    "styles.css",
    "app.js",
    "backend_app.py",
    "api.md",
    "backend_tests.md",
    "review.md",
}
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


def visible_agent_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        for key in ("text", "code", "url", "title", "description", "filename"):
            value = block.get(key)
            if isinstance(value, str):
                parts.append(value)
        if block.get("type") == "tool_call":
            output = block.get("output_preview")
            if isinstance(output, str):
                parts.append(output)
    return "\n".join(parts)


def shell_command_text(events: list[dict[str, Any]]) -> str:
    commands: list[str] = []
    for event in events:
        if event.get("event") != "tool_call":
            continue
        data = event.get("data") or {}
        tool_name = str(data.get("tool_name") or "").lower()
        if tool_name not in {"bash", "shell", "run_command"}:
            continue
        arguments = data.get("tool_arguments") or data.get("arguments") or {}
        if not isinstance(arguments, dict):
            continue
        command = arguments.get("command")
        if isinstance(command, str):
            commands.append(command)
    return "\n".join(commands)


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


def tool_results_by_name(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    names_by_call_id: dict[str, str] = {}
    results: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        data = event.get("data") or {}
        if event.get("event") == "tool_call":
            call_id = data.get("call_id")
            tool_name = data.get("tool_name")
            if isinstance(call_id, str) and isinstance(tool_name, str):
                names_by_call_id[call_id] = tool_name
            continue
        if event.get("event") != "tool_result":
            continue
        call_id = data.get("call_id")
        if not isinstance(call_id, str):
            continue
        tool_name = names_by_call_id.get(call_id)
        if tool_name:
            results.setdefault(tool_name, []).append(event)
    return results


def parse_tool_json(event: dict[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {}
    data = event.get("data") or {}
    raw = data.get("tool_output")
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def file_by_basename(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in files:
        path = str(item.get("path", ""))
        name = path.rsplit("/", 1)[-1]
        if name and name not in result:
            result[name] = item
    return result


def read_workspace_file(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    path: str,
) -> str:
    response = client.get(f"/api/v1/workspaces/{conv_id}/files/{path}", headers=headers)
    response.raise_for_status()
    return response.text


def task_text(task: dict[str, Any]) -> str:
    return "\n".join(
        str(task.get(key) or "")
        for key in ("task_id", "agent_id", "title", "instruction", "expected_output")
    ).lower()


def find_task(tasks: list[dict[str, Any]], markers: tuple[str, ...]) -> dict[str, Any] | None:
    normalized_markers = tuple(marker.lower() for marker in markers)
    for task in tasks:
        text = task_text(task)
        if any(marker in text for marker in normalized_markers):
            return task
    return None


def find_task_by_id(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    for task in tasks:
        if task.get("task_id") == task_id:
            return task
    return None


def fullstack_parallel_report(run_detail: dict[str, Any]) -> dict[str, Any]:
    tasks = run_detail.get("tasks") if isinstance(run_detail, dict) else []
    events = run_detail.get("events") if isinstance(run_detail, dict) else []
    if not isinstance(tasks, list):
        tasks = []
    if not isinstance(events, list):
        events = []

    frontend_task = find_task_by_id(tasks, "frontend_impl") or find_task(
        tasks,
        ("index.html", "styles.css", "app.js", "前端"),
    )
    backend_task = find_task_by_id(tasks, "backend_impl") or find_task(
        tasks,
        ("backend_app.py", "api.md", "backend_tests.md", "后端"),
    )
    review_task = find_task_by_id(tasks, "review") or find_task(
        tasks,
        ("review.md", "审阅", "review"),
    )

    frontend_id = str(frontend_task.get("task_id")) if frontend_task else ""
    backend_id = str(backend_task.get("task_id")) if backend_task else ""
    review_deps = set(review_task.get("depends_on") or []) if review_task else set()
    frontend_deps = set(frontend_task.get("depends_on") or []) if frontend_task else set()
    backend_deps = set(backend_task.get("depends_on") or []) if backend_task else set()

    started_order = [
        str(event.get("task_id"))
        for event in events
        if event.get("event_type") == "task_started" and event.get("task_id")
    ]
    result_order = [
        str(event.get("task_id"))
        for event in events
        if event.get("event_type") == "task_result" and event.get("task_id")
    ]

    review_after_front_backend = False
    if review_task:
        review_id = str(review_task.get("task_id"))
        if (
            review_id in started_order
            and frontend_id in result_order
            and backend_id in result_order
        ):
            review_started = started_order.index(review_id)
            frontend_done = result_order.index(frontend_id)
            backend_done = result_order.index(backend_id)
            review_after_front_backend = (
                frontend_done < review_started and backend_done < review_started
            )
        elif frontend_id and backend_id:
            review_after_front_backend = {frontend_id, backend_id}.issubset(review_deps)

    independent_front_backend = (
        bool(frontend_task)
        and bool(backend_task)
        and backend_id not in frontend_deps
        and frontend_id not in backend_deps
    )
    review_depends_on_both = (
        bool(review_task)
        and bool(frontend_id)
        and bool(backend_id)
        and {frontend_id, backend_id}.issubset(review_deps)
    )

    return {
        "frontend_task": frontend_task,
        "backend_task": backend_task,
        "review_task": review_task,
        "frontend_backend_independent": independent_front_backend,
        "review_depends_on_frontend_backend": review_depends_on_both,
        "review_after_frontend_backend": review_after_front_backend,
        "task_started_order": started_order,
        "task_result_order": result_order,
        "passed": bool(
            frontend_task
            and backend_task
            and review_task
            and independent_front_backend
            and review_depends_on_both
            and review_after_front_backend
        ),
    }


def main() -> None:
    started_at = time.time()
    SSE_PATH.write_text("", encoding="utf-8")
    report: dict[str, Any] = {
        "started_at": utc_now(),
        "base_url": BASE_URL,
        "account": USERNAME,
        "scenario": SCENARIO,
        "prompt": PROMPT,
        "target_agent_ids": AGENT_IDS,
        "artifacts": {
            "sse_jsonl": str(SSE_PATH),
            "report_json": str(REPORT_PATH),
            "browser_report_json": str(BROWSER_REPORT_PATH),
        },
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
        agent_items: list[dict[str, Any]] = agents.json().get("items", [])
        agent_ids = {item.get("id") for item in agent_items}
        missing_agents = [agent_id for agent_id in AGENT_IDS if agent_id not in agent_ids]
        report["checks"]["target_agents_present"] = not missing_agents
        if missing_agents:
            raise RuntimeError(f"missing target agents: {missing_agents}")
        orchestrator_item: dict[str, Any] = next(
            (item for item in agent_items if item.get("id") == "orchestrator"),
            {},
        )
        orchestrator_config = orchestrator_item.get("config") or {}
        report["orchestrator_config"] = orchestrator_config
        report["checks"]["orchestrator_llm_planning_enabled"] = (
            orchestrator_config.get("llm_planning") is True
        )
        report["checks"]["orchestrator_parallel_enabled"] = (
            orchestrator_config.get("orchestrator_parallel_enabled") is True
        )
        report["checks"]["orchestrator_parallel_concurrency_3"] = (
            orchestrator_config.get("orchestrator_parallel_max_concurrency") == 3
        )

        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json={
                "title": (
                    f"Orchestrator Fullstack Flow {int(started_at)}"
                    if FULLSTACK_SCENARIO
                    else f"Orchestrator Real Flow 8082 Demo {int(started_at)}"
                ),
                "mode": "group",
                "agent_ids": AGENT_IDS,
            },
        )
        conversation.raise_for_status()
        conv = conversation.json()
        conv_id = conv["id"]
        report["conversation"] = conv
        report["conversation_id"] = conv_id

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
        tool_results = tool_results_by_name(events)

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
                run_id = run_items[0].get("id")
                run_detail: dict[str, Any] = {}
                if isinstance(run_id, str):
                    detail = client.get(
                        f"/api/v1/conversations/{conv_id}/orchestrator-runs/{run_id}",
                        headers=headers,
                    )
                    if detail.status_code == 200:
                        run_detail = detail.json()
                        report["orchestrator_run_detail"] = run_detail
                        report["parallel_tasks"] = fullstack_parallel_report(run_detail)
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
        files_by_name = file_by_basename(files)
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
        if FULLSTACK_SCENARIO:
            missing_fullstack_files = sorted(REQUIRED_FULLSTACK_FILES - file_names)
            report["checks"]["workspace_has_required_fullstack_files"] = (
                not missing_fullstack_files
            )
            if missing_fullstack_files:
                report["bugs"].append(
                    {
                        "code": "missing_required_fullstack_files",
                        "symptom": (
                            "Workspace did not contain the required fullstack "
                            "delivery artifacts."
                        ),
                        "missing": missing_fullstack_files,
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
            if FULLSTACK_SCENARIO:
                report["checks"]["html_has_okr_product"] = bool(
                    re.search(r"OKR|目标|Objective|Key Result|看板|团队", html_text, re.I)
                )
                report["checks"]["html_links_css_js"] = (
                    "styles.css" in html_text and "app.js" in html_text
                )
                if not all(
                    report["checks"].get(key, False)
                    for key in ("html_has_okr_product", "html_links_css_js")
                ):
                    report["bugs"].append(
                        {
                            "code": "frontend_artifact_missing_fullstack_product_markers",
                            "symptom": (
                                "The entry HTML did not look like the requested "
                                "team OKR product or did not link CSS/JS artifacts."
                            ),
                            "checks": {
                                key: report["checks"].get(key, False)
                                for key in ("html_has_okr_product", "html_links_css_js")
                            },
                            "entry_html": entry["path"],
                        }
                    )
            else:
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
            report["checks"]["formal_preview_tool_called"] = any(
                str(block.get("call_id", "")).startswith("orch.quality.")
                for block in preview_tool_blocks
            )
            report["checks"]["platform_preview_tool_succeeded"] = any(
                block.get("status") == "ok" for block in preview_tool_blocks
            )
            verify_tool_blocks = [
                block
                for block in content_blocks
                if block.get("type") == "tool_call"
                and block.get("tool_name") == "verify_web_preview"
            ]
            report["checks"]["browser_verify_tool_called"] = bool(verify_tool_blocks)
            report["checks"]["formal_browser_verify_tool_called"] = any(
                str(block.get("call_id", "")).startswith("orch.quality.")
                for block in verify_tool_blocks
            )
            report["checks"]["browser_verify_tool_succeeded"] = any(
                block.get("status") == "ok" for block in verify_tool_blocks
            )
            report["checks"]["preview_url_in_agent_message"] = bool(
                preview_message_blocks
                and isinstance(preview_message_blocks[0].get("url"), str)
                and preview_message_blocks[0]["url"].startswith("http")
            )

            verify_events = tool_results.get("verify_web_preview", [])
            browser_report = parse_tool_json(verify_events[-1] if verify_events else None)
            if browser_report:
                report["browser_verification"] = browser_report
                write_json(BROWSER_REPORT_PATH, browser_report)
            screenshots = browser_report.get("screenshots") if browser_report else {}
            if not isinstance(screenshots, dict):
                screenshots = {}
            checks = browser_report.get("checks") if browser_report else {}
            if not isinstance(checks, dict):
                checks = {}
            report["checks"]["browser_verify_passed"] = (
                browser_report.get("passed") is True if browser_report else False
            )
            report["checks"]["browser_desktop_screenshot_exists"] = Path(
                str(screenshots.get("desktop", ""))
            ).exists()
            report["checks"]["browser_mobile_screenshot_exists"] = Path(
                str(screenshots.get("mobile", ""))
            ).exists()
            report["checks"]["browser_no_console_errors"] = (
                checks.get("no_console_errors") is True
            )
            report["checks"]["browser_no_page_errors"] = checks.get("no_page_errors") is True
            report["checks"]["browser_no_failed_requests"] = (
                checks.get("no_failed_requests") is True
            )
            report["checks"]["browser_mobile_no_horizontal_overflow"] = (
                checks.get("mobile_no_horizontal_overflow") is not False
            )
            click_checks = [
                value for key, value in checks.items() if key.endswith("_click_targets_ok")
            ]
            report["checks"]["browser_button_interaction_ok"] = (
                bool(click_checks) and all(value is True for value in click_checks)
            )
            failed_verify_events = [
                event
                for event in verify_events[:-1]
                if (event.get("data") or {}).get("tool_status") == "error"
            ]
            report["checks"]["browser_repaired_if_needed"] = (
                not failed_verify_events
                or (
                    report["checks"]["browser_verify_passed"]
                    and len(report["agent_switch_to_agents"]) >= 2
                )
            )

            preview = client.get(
                f"/api/v1/workspaces/{conv_id}/preview",
                headers=headers,
            )
            report["preview_get_status_code"] = preview.status_code
            if preview.status_code == 200:
                preview_body = preview.json()
                report["preview_8082"] = preview_body
                report["preview_url"] = preview_body.get("url")
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
                    "formal_preview_tool_called",
                    "browser_verify_tool_called",
                    "formal_browser_verify_tool_called",
                    "browser_verify_tool_succeeded",
                    "browser_verify_passed",
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

        if FULLSTACK_SCENARIO:
            planning_item = files_by_name.get("planning.md")
            review_item = files_by_name.get("review.md")
            api_item = files_by_name.get("api.md")
            backend_tests_item = files_by_name.get("backend_tests.md")
            review_text = (
                read_workspace_file(client, conv_id, headers, str(review_item["path"]))
                if review_item
                else ""
            )
            planning_text = (
                read_workspace_file(client, conv_id, headers, str(planning_item["path"]))
                if planning_item
                else ""
            )
            api_text = (
                read_workspace_file(client, conv_id, headers, str(api_item["path"]))
                if api_item
                else ""
            )
            backend_tests_text = (
                read_workspace_file(client, conv_id, headers, str(backend_tests_item["path"]))
                if backend_tests_item
                else ""
            )
            report["checks"]["planning_mentions_frontend_backend"] = bool(
                re.search(r"前端|frontend", planning_text, re.I)
                and re.search(r"后端|backend|API", planning_text, re.I)
            )
            report["checks"]["api_doc_mentions_okr_api"] = bool(
                re.search(r"OKR|目标|objective|key result|API|接口", api_text, re.I)
            )
            report["checks"]["backend_tests_has_test_plan"] = bool(
                re.search(r"测试|test|pytest|验收", backend_tests_text, re.I)
            )
            report["checks"]["review_checks_api_consistency"] = bool(
                re.search(r"接口|API|一致", review_text, re.I)
            )
            report["checks"]["review_has_test_or_risk"] = bool(
                re.search(r"测试|风险|建议|risk|test", review_text, re.I)
            )
            parallel_tasks = report.get("parallel_tasks")
            report["checks"]["fullstack_parallel_dag"] = (
                isinstance(parallel_tasks, dict) and parallel_tasks.get("passed") is True
            )
            report["known_limits"] = [
                "Backend service deployment is not part of this platform preview test; "
                "backend is validated as workspace source code, API documentation, "
                "test notes, and review evidence."
            ]
            fullstack_quality_checks = (
                "planning_mentions_frontend_backend",
                "api_doc_mentions_okr_api",
                "backend_tests_has_test_plan",
                "review_checks_api_consistency",
                "review_has_test_or_risk",
                "fullstack_parallel_dag",
            )
            if not all(report["checks"].get(key, False) for key in fullstack_quality_checks):
                report["bugs"].append(
                    {
                        "code": "fullstack_review_or_parallel_validation_failed",
                        "symptom": (
                            "Fullstack delivery artifacts, review evidence, or DAG "
                            "parallel validation did not satisfy the test plan."
                        ),
                        "checks": {
                            key: report["checks"].get(key, False)
                            for key in fullstack_quality_checks
                        },
                        "parallel_tasks": report.get("parallel_tasks"),
                    }
                )
            report["warnings"].append(
                {
                    "code": "backend_not_deployed_by_platform",
                    "message": (
                        "Backend code is generated and reviewed, but the current "
                        "platform preview only publishes the static frontend."
                    ),
                }
            )

        message_blocks = (target or {}).get("content") or []
        text = block_text(message_blocks)
        server_command_scan_text = "\n".join(
            part
            for part in (visible_agent_text(message_blocks), shell_command_text(events))
            if part
        )
        report["server_command_scan_text_length"] = len(server_command_scan_text)
        report["checks"]["agent_output_no_long_running_server_command"] = (
            SERVER_COMMAND_RE.search(server_command_scan_text) is None
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
            "target_agents_present": report["checks"].get("target_agents_present", False),
            "orchestrator_llm_planning_enabled": report["checks"].get(
                "orchestrator_llm_planning_enabled",
                False,
            ),
            "orchestrator_parallel_enabled": report["checks"].get(
                "orchestrator_parallel_enabled",
                False,
            ),
            "orchestrator_parallel_concurrency_3": report["checks"].get(
                "orchestrator_parallel_concurrency_3",
                False,
            ),
            "message_done": report["checks"].get("message_done", False),
            "planner_used_llm": report["checks"].get("planner_used_llm", False),
            "has_html_artifact": report["checks"].get("has_html_artifact", False),
            "workspace_has_required_frontend_files": report["checks"].get(
                "workspace_has_required_frontend_files",
                False,
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
            "formal_preview_tool_called": report["checks"].get(
                "formal_preview_tool_called",
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
            "browser_verify_tool_called": report["checks"].get(
                "browser_verify_tool_called",
                False,
            ),
            "formal_browser_verify_tool_called": report["checks"].get(
                "formal_browser_verify_tool_called",
                False,
            ),
            "browser_verify_tool_succeeded": report["checks"].get(
                "browser_verify_tool_succeeded",
                False,
            ),
            "browser_verify_passed": report["checks"].get("browser_verify_passed", False),
            "browser_desktop_screenshot_exists": report["checks"].get(
                "browser_desktop_screenshot_exists",
                False,
            ),
            "browser_mobile_screenshot_exists": report["checks"].get(
                "browser_mobile_screenshot_exists",
                False,
            ),
            "browser_no_console_errors": report["checks"].get(
                "browser_no_console_errors",
                False,
            ),
            "browser_no_page_errors": report["checks"].get(
                "browser_no_page_errors",
                False,
            ),
            "browser_no_failed_requests": report["checks"].get(
                "browser_no_failed_requests",
                False,
            ),
            "browser_mobile_no_horizontal_overflow": report["checks"].get(
                "browser_mobile_no_horizontal_overflow",
                False,
            ),
            "browser_button_interaction_ok": report["checks"].get(
                "browser_button_interaction_ok",
                False,
            ),
            "browser_repaired_if_needed": report["checks"].get(
                "browser_repaired_if_needed",
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
        if FULLSTACK_SCENARIO:
            hard_checks.update(
                {
                    "workspace_has_required_fullstack_files": report["checks"].get(
                        "workspace_has_required_fullstack_files",
                        False,
                    ),
                    "html_has_okr_product": report["checks"].get(
                        "html_has_okr_product",
                        False,
                    ),
                    "html_links_css_js": report["checks"].get(
                        "html_links_css_js",
                        False,
                    ),
                    "planning_mentions_frontend_backend": report["checks"].get(
                        "planning_mentions_frontend_backend",
                        False,
                    ),
                    "api_doc_mentions_okr_api": report["checks"].get(
                        "api_doc_mentions_okr_api",
                        False,
                    ),
                    "backend_tests_has_test_plan": report["checks"].get(
                        "backend_tests_has_test_plan",
                        False,
                    ),
                    "review_checks_api_consistency": report["checks"].get(
                        "review_checks_api_consistency",
                        False,
                    ),
                    "review_has_test_or_risk": report["checks"].get(
                        "review_has_test_or_risk",
                        False,
                    ),
                    "fullstack_parallel_dag": report["checks"].get(
                        "fullstack_parallel_dag",
                        False,
                    ),
                }
            )
        else:
            hard_checks["artifact_covers_required_sections"] = all(
                report["checks"].get(key, False)
                for key in (
                    "html_has_task_breakdown",
                    "html_has_code_artifact",
                    "html_has_diff",
                    "html_has_preview",
                )
            )
        report["acceptance"] = {**hard_checks, "passed": all(hard_checks.values())}

    report["finished_at"] = utc_now()
    report["duration_seconds"] = round(time.time() - started_at, 3)
    report["passed"] = bool(report.get("acceptance", {}).get("passed"))
    write_json(REPORT_PATH, report)
    print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
    print(f"report={REPORT_PATH}")
    print(f"browser_report={BROWSER_REPORT_PATH}")
    print(f"sse={SSE_PATH}")


if __name__ == "__main__":
    main()
