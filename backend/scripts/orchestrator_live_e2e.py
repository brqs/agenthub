"""Run the deployed Orchestrator 8082 demo flow and write a JSON report.

This script intentionally uses the same HTTP API surface as the deployed frontend.
It is opt-in and intended for manual/live verification, not default CI.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

BASE_URL = os.getenv("AGENTHUB_E2E_BASE_URL", "http://154.44.25.94:1573")
USERNAME = os.getenv("AGENTHUB_E2E_USERNAME", "12345678")
PASSWORD = os.getenv("AGENTHUB_E2E_PASSWORD", "12345678")
SCENARIO = os.getenv("AGENTHUB_E2E_SCENARIO", "quality").strip().lower()
P1_ATTRIBUTION_SCENARIO = SCENARIO == "p1_attribution"
P1_WORKFLOW_SCENARIO = SCENARIO == "p1_workflow"
P1_WORKFLOW_RUNTIME_SCENARIO = SCENARIO == "p1_workflow_runtime"
P1_REVIEW_THREAD_SCENARIO = SCENARIO == "p1_review_thread_repair"
P1_RICH_ARTIFACTS_SCENARIO = SCENARIO == "p1_rich_artifacts"
P1_EVALUATION_REPAIR_SCENARIO = SCENARIO == "p1_evaluation_repair"
P1_AGENT_CAPABILITY_PROFILE_SCENARIO = SCENARIO == "p1_agent_capability_profile"
P1_SCENARIO = (
    P1_ATTRIBUTION_SCENARIO
    or P1_WORKFLOW_SCENARIO
    or P1_WORKFLOW_RUNTIME_SCENARIO
    or P1_REVIEW_THREAD_SCENARIO
    or P1_RICH_ARTIFACTS_SCENARIO
    or P1_EVALUATION_REPAIR_SCENARIO
    or P1_AGENT_CAPABILITY_PROFILE_SCENARIO
)
FULLSTACK_SCENARIO = SCENARIO == "fullstack"
DEPLOYMENT_REPAIR_SCENARIO = SCENARIO == "deployment_repair"
CUSTOM_AGENT_TOOLS_SCENARIO = SCENARIO == "custom_agent_tools"
DEPLOYMENT_SCENARIO = SCENARIO in {"deployment", "deployment_repair"}
DEFAULT_P1_ATTRIBUTION_SSE_PATH = "/tmp/agenthub_p1_attribution_sse.jsonl"  # noqa: S108
DEFAULT_P1_WORKFLOW_SSE_PATH = "/tmp/agenthub_p1_workflow_sse.jsonl"  # noqa: S108
DEFAULT_P1_WORKFLOW_RUNTIME_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_workflow_runtime_sse.jsonl"  # noqa: S108
)
DEFAULT_P1_REVIEW_THREAD_SSE_PATH = "/tmp/agenthub_p1_review_thread_sse.jsonl"  # noqa: S108
DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_rich_artifacts_sse.jsonl"  # noqa: S108
)
DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_evaluation_repair_sse.jsonl"  # noqa: S108
)
DEFAULT_P1_AGENT_CAPABILITY_PROFILE_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_agent_capability_profile_sse.jsonl"  # noqa: S108
)
DEFAULT_FULLSTACK_SSE_PATH = "/tmp/agenthub_fullstack_flow_sse.jsonl"  # noqa: S108
DEFAULT_QUALITY_SSE_PATH = "/tmp/agenthub_orchestrator_quality_sse.jsonl"  # noqa: S108
DEFAULT_DEPLOYMENT_SSE_PATH = "/tmp/agenthub_deployment_flow_sse.jsonl"  # noqa: S108
DEFAULT_DEPLOYMENT_REPAIR_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_deployment_repair_flow_sse.jsonl"  # noqa: S108
)
DEFAULT_CUSTOM_AGENT_TOOLS_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_custom_agent_tools_sse.jsonl"  # noqa: S108
)
DEFAULT_P1_ATTRIBUTION_REPORT_PATH = "/tmp/agenthub_p1_attribution_report.json"  # noqa: S108
DEFAULT_P1_WORKFLOW_REPORT_PATH = "/tmp/agenthub_p1_workflow_report.json"  # noqa: S108
DEFAULT_P1_WORKFLOW_RUNTIME_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_workflow_runtime_report.json"  # noqa: S108
)
DEFAULT_P1_REVIEW_THREAD_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_review_thread_report.json"  # noqa: S108
)
DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_rich_artifacts_report.json"  # noqa: S108
)
DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_evaluation_repair_report.json"  # noqa: S108
)
DEFAULT_P1_AGENT_CAPABILITY_PROFILE_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_agent_capability_profile_report.json"  # noqa: S108
)
DEFAULT_FULLSTACK_REPORT_PATH = "/tmp/agenthub_fullstack_flow_report.json"  # noqa: S108
DEFAULT_QUALITY_REPORT_PATH = "/tmp/agenthub_orchestrator_quality_report.json"  # noqa: S108
DEFAULT_DEPLOYMENT_REPORT_PATH = "/tmp/agenthub_deployment_flow_report.json"  # noqa: S108
DEFAULT_DEPLOYMENT_REPAIR_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_deployment_repair_flow_report.json"  # noqa: S108
)
DEFAULT_CUSTOM_AGENT_TOOLS_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_custom_agent_tools_report.json"  # noqa: S108
)
DEFAULT_FULLSTACK_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_fullstack_flow_browser.json"  # noqa: S108
)
DEFAULT_QUALITY_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_quality_browser.json"  # noqa: S108
)
DEFAULT_DEPLOYMENT_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_deployment_flow_browser.json"  # noqa: S108
)
DEFAULT_DEPLOYMENT_REPAIR_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_deployment_repair_flow_browser.json"  # noqa: S108
)
SSE_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_SSE_PATH",
        (
            DEFAULT_P1_ATTRIBUTION_SSE_PATH
            if P1_ATTRIBUTION_SCENARIO
            else DEFAULT_P1_WORKFLOW_SSE_PATH
            if P1_WORKFLOW_SCENARIO
            else DEFAULT_P1_WORKFLOW_RUNTIME_SSE_PATH
            if P1_WORKFLOW_RUNTIME_SCENARIO
            else DEFAULT_P1_REVIEW_THREAD_SSE_PATH
            if P1_REVIEW_THREAD_SCENARIO
            else DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH
            if P1_RICH_ARTIFACTS_SCENARIO
            else DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH
            if P1_EVALUATION_REPAIR_SCENARIO
            else DEFAULT_P1_AGENT_CAPABILITY_PROFILE_SSE_PATH
            if P1_AGENT_CAPABILITY_PROFILE_SCENARIO
            else DEFAULT_FULLSTACK_SSE_PATH
            if FULLSTACK_SCENARIO
            else DEFAULT_CUSTOM_AGENT_TOOLS_SSE_PATH
            if CUSTOM_AGENT_TOOLS_SCENARIO
            else DEFAULT_DEPLOYMENT_REPAIR_SSE_PATH
            if DEPLOYMENT_REPAIR_SCENARIO
            else DEFAULT_DEPLOYMENT_SSE_PATH
            if DEPLOYMENT_SCENARIO
            else DEFAULT_QUALITY_SSE_PATH
        ),
    )
)
REPORT_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_REPORT_PATH",
        (
            DEFAULT_P1_ATTRIBUTION_REPORT_PATH
            if P1_ATTRIBUTION_SCENARIO
            else DEFAULT_P1_WORKFLOW_REPORT_PATH
            if P1_WORKFLOW_SCENARIO
            else DEFAULT_P1_WORKFLOW_RUNTIME_REPORT_PATH
            if P1_WORKFLOW_RUNTIME_SCENARIO
            else DEFAULT_P1_REVIEW_THREAD_REPORT_PATH
            if P1_REVIEW_THREAD_SCENARIO
            else DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH
            if P1_RICH_ARTIFACTS_SCENARIO
            else DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH
            if P1_EVALUATION_REPAIR_SCENARIO
            else DEFAULT_P1_AGENT_CAPABILITY_PROFILE_REPORT_PATH
            if P1_AGENT_CAPABILITY_PROFILE_SCENARIO
            else DEFAULT_FULLSTACK_REPORT_PATH
            if FULLSTACK_SCENARIO
            else DEFAULT_CUSTOM_AGENT_TOOLS_REPORT_PATH
            if CUSTOM_AGENT_TOOLS_SCENARIO
            else DEFAULT_DEPLOYMENT_REPAIR_REPORT_PATH
            if DEPLOYMENT_REPAIR_SCENARIO
            else DEFAULT_DEPLOYMENT_REPORT_PATH
            if DEPLOYMENT_SCENARIO
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
            else DEFAULT_DEPLOYMENT_REPAIR_BROWSER_REPORT_PATH
            if DEPLOYMENT_REPAIR_SCENARIO
            else DEFAULT_DEPLOYMENT_BROWSER_REPORT_PATH
            if DEPLOYMENT_SCENARIO
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
DEPLOYMENT_PROMPT = (
    "@orchestrator 请生成一个“团队 OKR 轻量看板”静态前端产品，包含 "
    "index.html、styles.css、app.js 和 Dockerfile，Dockerfile 使用 nginx 静态服务并 "
    "EXPOSE 80。页面中需要清晰展示任务拆解、代码产物、Diff、网页预览、按钮交互"
    "和移动端适配。完成后请部署发布到端口8082，返回部署状态卡片、访问 URL，"
    "并额外打包源码供下载。最后请执行容器化部署并返回容器 URL，同时完成浏览器级"
    "质量验收。"
)
DEPLOYMENT_REPAIR_PROMPT = (
    "@orchestrator 当前 workspace 已经有完整可用的 index.html、styles.css、app.js，"
    "以及一个故意有问题的 Dockerfile。首次容器部署前不要修改任何 workspace 文件，"
    "也不要让子 Agent 先修复 Dockerfile；请先只在端口8082执行浏览器级质量验收、静态发布、"
    "源码打包和 create_deployment(kind=container)。当 deployment_health 失败后，"
    "再由 reflection/repair agent 根据 deployment logs 修复 Dockerfile 或应用健康检查路由，"
    "然后重新调用 create_deployment(kind=container)，直到返回 published 的容器 URL。"
    "不要手动运行 Docker 或启动长驻服务。"
)
CUSTOM_AGENT_TOOLS_PROMPT = (
    "@orchestrator 请创建一个新的自建 Agent，名字为 LiveReader-{timestamp}，"
    "provider 使用 builtin，system_prompt 为“你是一个只能读取 workspace 文件的中文"
    "检查 Agent；需要文件内容时必须使用 read_file 工具；不能写文件或运行命令”，"
    "capabilities 设置为 reading、review，工具白名单设置为 read_file，并把它加入当前群聊。"
)
P1_ATTRIBUTION_PROMPT = (
    "@orchestrator 请进行 P1-1 合流消息归属验收。请只做 markdown 协作记录。"
    "明确拆成两个互不依赖的实现任务：让 claude-code 创建 p1-attribution-claude.md，"
    "内容包含“CLAUDE_ATTRIBUTION_SENTINEL”；让 opencode-helper 创建 "
    "p1-attribution-opencode.md，内容包含“OPENCODE_ATTRIBUTION_SENTINEL”。"
    "两个成员都需要简短说明自己完成的文件。最后由 orchestrator 汇总，说明两个"
    "不同成员的结果都已完成。不要在可见回复里用 @claude-code 或 @opencode-helper "
    "这种纯文本标题来表达归属，归属必须依赖 stream/message block 的 agent_id。"
)
P1_WORKFLOW_PROMPT = (
    "@orchestrator 请进行 P1-2 Workflow ContentBlock 验收。只调度 codex-helper 完成："
    "创建 workspace 文件 p1-workflow.yaml，并在回复中输出同一份合法 workflow-yaml fenced "
    "block。Workflow 必须包含 version、name、nodes、edges，name 为 P1 Workflow E2E，"
    "nodes 至少包含 start(trigger)、review(action)、publish(action)。edges 中每条边"
    "必须使用字段 source 和 target，不要使用 from/to；两条边分别是 source: start / "
    "target: review，以及 source: review / target: publish。仅生成 YAML 文件和文字说明。"
    "最终总结确认 "
    "p1-workflow.yaml 已生成且 workflow_validation 通过。"
)
P1_WORKFLOW_RUNTIME_PROMPT = (
    "@orchestrator 请进行 P1-B2-01 Workflow runtime / dry-run 验收。只调度 "
    "codex-helper 完成：创建 workspace 文件 p1-runtime-workflow.yaml，并在回复中"
    "输出同一份合法 workflow-yaml fenced block。Workflow 必须包含 version、name、"
    "nodes、edges，name 为 P1 Workflow Runtime E2E。nodes 必须依次包含："
    "start(trigger)、set_context(task，config.action=set_context，config.values.release.status=ready)、"
    "check(assert，config.equals.release.status=ready)、done(end)。edges 使用 source/target，"
    "依次连接 start -> set_context -> check -> done。不要使用 shell、HTTP、部署或外部服务。"
    "最终总结必须确认 p1-runtime-workflow.yaml 已生成、workflow_validation passed、"
    "workflow dry-run passed。"
)
P1_REVIEW_THREAD_PROMPT = (
    "@orchestrator 请进行 P1-3 Agent-to-Agent Review Thread / repair 验收。只使用当前"
    "群聊成员。请先让 claude-code 创建 p1-review-thread.md，但首次实现必须故意只写"
    "标题和 TODO，明确不要写 REQUIRED_E2E_REPAIR_SECTION。随后由 codex-helper 作为"
    "独立 review agent 审核该产物；如果缺少 REQUIRED_E2E_REPAIR_SECTION，review 回复"
    "第一行必须是 review_outcome: needs_repair，并说明需要原实现 Agent 修复。"
    "Orchestrator 收到 needs_repair 后必须追加 repair task，让原实现 Agent 补上 "
    "REQUIRED_E2E_REPAIR_SECTION 和修复说明。最终总结必须包含 review_of、handoff、"
    "review outcome: needs_repair，并确认最终消息完成。仅生成 markdown 文件和文字审核。"
)
P1_RICH_ARTIFACTS_PROMPT = (
    "@orchestrator 请进行 P1 Rich Artifact API/SSE 验收。只允许规划下列四个"
    "workspace 文件任务。任务一：claude-code 创建 "
    "docs/rich-report.md，内容必须是"
    "完整 markdown 报告。任务二：claude-code 创建 slides/rich-deck.md，内容是幻灯片"
    "大纲；该路径用于归类为 ppt artifact。任务三：opencode-helper 创建 "
    "assets/rich-logo.svg，必须是有效 SVG。任务四：opencode-helper 创建 "
    "packages/rich-export.tar，必须是有效 tar archive；请用 shell 创建 "
    "packages/rich-export/README.md，然后执行 "
    "`tar -cf packages/rich-export.tar -C packages/rich-export README.md`，"
    "并用 `tar -tf packages/rich-export.tar` 验证 README.md 条目存在。"
    "四个文件都必须真实存在，并在最终消息中保留 file block。最终总结只列出这四个 "
    "artifact path、artifact kind 和负责 agent。"
)
P1_EVALUATION_REPAIR_PROMPT = (
    "@orchestrator 请进行 P1 Evaluation Repair 验收。只规划一个 markdown 文档任务："
    "claude-code 创建 repair-report.md。Agent invocation 协议必须如下：如果本次调用"
    "没有系统上下文标题 `Previous sub-agent results:` 或 `Previous attempt failure:`，"
    "只写两行 TODO markdown 并立即结束，让 document_quality failed 和 reflection 发生；"
    "如果本次调用带有上一轮 evaluation failed / repair instruction，再重写 repair-report.md："
    "加入 # Repair Report "
    "标题、Summary、Validation Evidence、Required E2E Repair Section、Final Status 四个"
    "章节，每个章节都有正文，不留空标题，不写 TODO/placeholder。最终总结必须说明 "
    "document_quality failed -> fallback/repair -> final passed 或 manual_review_required，"
    "并明确 manifest 不应把 failed artifact 标成 passed。"
)
P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT = (
    "@orchestrator 请进行 Agent Capability Profile 种子轮。只规划一个 markdown 文档任务："
    "claude-code 创建 capability-seed.md。Agent invocation 协议必须如下：如果本次调用"
    "没有系统上下文标题 `Previous sub-agent results:` 或 `Previous attempt failure:`，"
    "只允许一次 Write，写入标题和 `TODO: CAPABILITY_PROFILE_SEED_INCOMPLETE` 后立即结束；"
    "不得继续解释、再次 Write、自行评估、自行修复或模拟 fallback，让 runtime 的 "
    "document_quality 产生 evaluation_failed。"
    "如果本次调用带有上一轮 evaluation failed / repair instruction，则完整重写 "
    "capability-seed.md，加入背景、修复步骤、验证结果三节和 "
    "CAPABILITY_PROFILE_SEED_REPAIRED_SENTINEL，不留 TODO/placeholder。"
    "初始任务必须分配给 claude-code。evaluation 和 fallback 只能由 Orchestrator runtime "
    "在当前 Agent 调用结束后处理；repair 必须作为同一个逻辑任务的 retry/fallback attempt，"
    "禁止为 repair 另建任务，禁止新增 review task，整个 seed run 必须只有一个 task。"
    "不要预览、不要部署。"
)
P1_AGENT_CAPABILITY_PROFILE_PROMPT = (
    "@orchestrator 请进行 Agent Capability Profile 后续规划验收。基于当前 conversation "
    "已有历史 run 的 Agent capability profile，自主选择一个近期成功的文档 Agent 创建 "
    "capability-followup.md，内容必须包含 CAPABILITY_PROFILE_FOLLOWUP_SENTINEL。"
    "最终总结必须明确出现 Agent capability profile from recent Orchestrator runs、"
    "capability profile、recent success、选择依据、被选择 agent id。请求中没有指定"
    "具体执行 Agent，必须根据画像完成软选择。只规划一个逻辑文档任务，禁止新增 review "
    "或 verification task；不要先让画像较弱的 Agent 尝试再 fallback，唯一 task 及其"
    "所有实际 attempt 都应由画像显示近期成功的 Agent 执行。不要预览、不要部署。"
)

PROMPT = os.getenv(
    "AGENTHUB_E2E_PROMPT",
    P1_ATTRIBUTION_PROMPT
    if P1_ATTRIBUTION_SCENARIO
    else P1_WORKFLOW_PROMPT
    if P1_WORKFLOW_SCENARIO
    else P1_WORKFLOW_RUNTIME_PROMPT
    if P1_WORKFLOW_RUNTIME_SCENARIO
    else P1_REVIEW_THREAD_PROMPT
    if P1_REVIEW_THREAD_SCENARIO
    else P1_RICH_ARTIFACTS_PROMPT
    if P1_RICH_ARTIFACTS_SCENARIO
    else P1_EVALUATION_REPAIR_PROMPT
    if P1_EVALUATION_REPAIR_SCENARIO
    else P1_AGENT_CAPABILITY_PROFILE_PROMPT
    if P1_AGENT_CAPABILITY_PROFILE_SCENARIO
    else FULLSTACK_PROMPT
    if FULLSTACK_SCENARIO
    else CUSTOM_AGENT_TOOLS_PROMPT.format(timestamp=int(time.time()))
    if CUSTOM_AGENT_TOOLS_SCENARIO
    else DEPLOYMENT_REPAIR_PROMPT
    if DEPLOYMENT_REPAIR_SCENARIO
    else DEPLOYMENT_PROMPT
    if DEPLOYMENT_SCENARIO
    else (
        "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff、网页预览、"
        "按钮交互和移动端适配的前端开发演示，主题随机，部署在端口8082，"
        "并完成浏览器级质量验收"
    ),
)
AGENT_IDS = ["orchestrator", "claude-code", "opencode-helper", "codex-helper"]
P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS = [
    "orchestrator",
    "claude-code",
    "opencode-helper",
]
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
    r"app\.listen\s*\(|express\s+server",
    re.I,
)
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


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def normalize_http_url(raw_url: Any) -> str | None:
    if not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    if not url:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        return url
    if url.startswith("//"):
        return f"http:{url}"
    return f"http://{url.lstrip('/')}"


def cleanup_previous_preview(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
) -> None:
    if os.getenv("AGENTHUB_E2E_SKIP_PREVIEW_CLEANUP", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        report["preflight_preview_cleanup"] = {"skipped": True}
        return
    if not REPORT_PATH.exists():
        return
    try:
        previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report["preflight_preview_cleanup"] = {"error": str(exc)}
        return
    conversation_id = previous.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        return
    try:
        response = client.delete(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
        )
    except httpx.HTTPError as exc:
        report["preflight_preview_cleanup"] = {
            "conversation_id": conversation_id,
            "error": str(exc),
        }
        return
    report["preflight_preview_cleanup"] = {
        "conversation_id": conversation_id,
        "status_code": response.status_code,
        "ok": response.status_code in {200, 404},
    }


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


def send_message_and_stream(
    client: httpx.Client,
    headers: dict[str, str],
    conversation_id: str,
    *,
    content: str,
    target_agent_id: str,
    started_at: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    send = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": content}],
            "target_agent_id": target_agent_id,
        },
    )
    send.raise_for_status()
    sent = send.json()
    agent_message_id = sent["agent_message"]["id"]
    with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as stream:
        stream.raise_for_status()
        events = parse_sse(stream, started_at)
    messages = client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers)
    messages.raise_for_status()
    items = messages.json().get("items", [])
    target = next((item for item in items if item.get("id") == agent_message_id), None)
    return sent, events, target


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


def list_workflow_runs(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    path: str,
) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/v1/workspaces/{conv_id}/workflow-runs",
        headers=headers,
        params={"path": path},
    )
    response.raise_for_status()
    body = response.json()
    items = body.get("items")
    return items if isinstance(items, list) else []


def get_workflow_run(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    run_id: str,
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/workspaces/{conv_id}/workflow-runs/{run_id}",
        headers=headers,
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def create_workflow_dry_run(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    path: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{conv_id}/workflow-runs",
        headers=headers,
        json={"path": path, "inputs": {}, "mode": "dry_run"},
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def get_workflow_health(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    path: str,
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/workspaces/{conv_id}/workflow-health",
        headers=headers,
        params={"path": path},
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def get_workspace_artifacts(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/workspaces/{conv_id}/artifacts", headers=headers)
    response.raise_for_status()
    body = response.json()
    items = body.get("items")
    return items if isinstance(items, list) else []


def put_workspace_file(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    path: str,
    content: str,
) -> None:
    response = client.put(
        f"/api/v1/workspaces/{conv_id}/files/{path}",
        headers=headers,
        content=content.encode("utf-8"),
    )
    response.raise_for_status()


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


def config_summary(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    keys = (
        "llm_planning",
        "orchestrator_parallel_enabled",
        "orchestrator_parallel_max_concurrency",
        "orchestrator_agent_review_enabled",
        "orchestrator_review_agent_ids",
        "agent_to_agent_review_enabled",
        "review_agent_ids",
        "orchestrator_memory_enabled",
    )
    return {key: config.get(key) for key in keys if key in config}


async def _patch_orchestrator_review_config(
    review_agent_ids: list[str],
) -> dict[str, Any]:
    from app.core.database import SessionFactory, engine
    from app.models.agent import Agent

    async with SessionFactory() as db:
        agent = await db.get(Agent, "orchestrator")
        if agent is None:
            raise RuntimeError("orchestrator agent not found")
        original_config = dict(agent.config or {})
        patched_config = {
            **original_config,
            "orchestrator_agent_review_enabled": True,
            "orchestrator_review_agent_ids": review_agent_ids,
        }
        agent.config = patched_config
        await db.commit()
    await engine.dispose()
    return original_config


async def _restore_orchestrator_config(config: dict[str, Any]) -> dict[str, Any]:
    from app.core.database import SessionFactory, engine
    from app.models.agent import Agent

    async with SessionFactory() as db:
        agent = await db.get(Agent, "orchestrator")
        if agent is None:
            raise RuntimeError("orchestrator agent not found")
        agent.config = dict(config)
        await db.commit()
    await engine.dispose()
    return {"restored": True, "restored_config_summary": config_summary(config)}


def event_data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def final_summary_from_report(report: dict[str, Any]) -> str:
    run_items = report.get("orchestrator_runs")
    if isinstance(run_items, list) and run_items:
        return "\n".join(str(item.get("final_summary") or "") for item in run_items)
    run_detail = report.get("orchestrator_run_detail")
    if isinstance(run_detail, dict):
        run = run_detail.get("run")
        if isinstance(run, dict):
            return str(run.get("final_summary") or "")
    return ""


def fetch_orchestrator_run_detail(
    client: httpx.Client,
    headers: dict[str, str],
    conv_id: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    runs = client.get(f"/api/v1/conversations/{conv_id}/orchestrator-runs", headers=headers)
    report["orchestrator_runs_status_code"] = runs.status_code
    if runs.status_code != 200:
        report["orchestrator_runs_error"] = runs.text
        return {}
    run_items = runs.json().get("items", [])
    report["orchestrator_runs"] = run_items
    if not run_items:
        return {}
    run_id = run_items[0].get("id")
    if not isinstance(run_id, str):
        return {}
    detail = client.get(
        f"/api/v1/conversations/{conv_id}/orchestrator-runs/{run_id}",
        headers=headers,
    )
    report["orchestrator_run_detail_status_code"] = detail.status_code
    if detail.status_code != 200:
        report["orchestrator_run_detail_error"] = detail.text
        return {}
    run_detail = detail.json()
    report["orchestrator_run_detail"] = run_detail
    return run_detail


def fetch_agent_capability_profile(
    client: httpx.Client,
    headers: dict[str, str],
    conv_id: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/conversations/{conv_id}/agent-capability-profile",
        headers=headers,
    )
    report["agent_capability_profile_status_code"] = response.status_code
    if response.status_code != 200:
        report["agent_capability_profile_error"] = response.text
        return {}
    profile = response.json()
    report["agent_capability_profile"] = profile
    return profile


def fetch_workspace_evidence(
    client: httpx.Client,
    headers: dict[str, str],
    conv_id: str,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    tree = client.get(f"/api/v1/workspaces/{conv_id}/tree", headers=headers)
    report["workspace_tree_status_code"] = tree.status_code
    if tree.status_code != 200:
        report["workspace_tree_error"] = tree.text
        return []
    report["workspace_tree"] = tree.json()
    files = flatten_tree(report["workspace_tree"]["tree"])
    report["workspace_files"] = files
    return files


def p1_content_blocks(report: dict[str, Any]) -> list[dict[str, Any]]:
    target = report.get("target_agent_message")
    if not isinstance(target, dict):
        return []
    blocks = target.get("content")
    return blocks if isinstance(blocks, list) else []


def p1_common_evidence(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
    *,
    title: str,
    agent_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": title,
            "mode": "group",
            "agent_ids": agent_ids,
        },
    )
    conversation.raise_for_status()
    conv = conversation.json()
    conv_id = conv["id"]
    report["conversation"] = conv
    report["conversation_id"] = conv_id

    sent, events, target = send_message_and_stream(
        client,
        headers,
        conv_id,
        content=PROMPT,
        target_agent_id="orchestrator",
        started_at=started_at,
    )
    report["user_message_id"] = sent["user_message"]["id"]
    report["agent_message_id"] = sent["agent_message"]["id"]
    report["target_agent_message"] = target
    report["stream_event_count"] = len(events)
    report["agent_switch_to_agents"] = [
        event_data(event).get("to_agent")
        for event in events
        if event.get("event") == "agent_switch"
    ]
    report["checks"]["message_done"] = bool(target and target.get("status") == "done")
    fetch_orchestrator_run_detail(client, headers, conv_id, report)
    files = fetch_workspace_evidence(client, headers, conv_id, report)
    report["content_block_types"] = [
        block.get("type") for block in p1_content_blocks(report)
    ]
    return events, files


def p1_agent_id_report(
    events: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    allowed_agents = set(AGENT_IDS)
    sub_agents = allowed_agents - {"orchestrator"}
    chunk_event_types = {"block_start", "delta", "block_end", "tool_call", "tool_result"}
    chunk_events = [
        event for event in events if str(event.get("event")) in chunk_event_types
    ]
    missing_or_invalid_chunk_events = [
        {
            "event": event.get("event"),
            "elapsed_seconds": event.get("elapsed_seconds"),
            "data": event_data(event),
        }
        for event in chunk_events
        if event_data(event).get("agent_id") not in allowed_agents
    ]
    child_chunk_agent_ids = sorted(
        {
            str(event_data(event).get("agent_id"))
            for event in chunk_events
            if event_data(event).get("agent_id") in sub_agents
        }
    )
    persisted_agent_blocks = [
        block
        for block in blocks
        if block.get("type") in {"text", "code", "diff", "tool_call", "workflow"}
    ]
    invalid_persisted_blocks = [
        block
        for block in persisted_agent_blocks
        if block.get("agent_id") not in allowed_agents
    ]
    child_block_agent_ids = sorted(
        {
            str(block.get("agent_id"))
            for block in persisted_agent_blocks
            if block.get("agent_id") in sub_agents
        }
    )
    visible_text = visible_agent_text(blocks)
    raw_header_matches = re.findall(
        r"(?m)^\s*@(claude-code|opencode-helper|codex-helper)\b",
        visible_text,
    )
    orchestration_blocks = [
        block
        for block in blocks
        if block.get("type") == "text"
        and block.get("agent_id") == "orchestrator"
        and re.search(
            r"Planned|Execution summary|执行总结|任务规划|sub-task",
            str(block.get("text") or ""),
            re.I,
        )
    ]
    plan_summary_wrong_agent_blocks = [
        block
        for block in blocks
        if block.get("type") == "text"
        and block.get("agent_id") != "orchestrator"
        and re.search(
            r"Planned|Execution summary|执行总结|任务规划|sub-task",
            str(block.get("text") or ""),
            re.I,
        )
    ]
    return {
        "chunk_event_count": len(chunk_events),
        "missing_or_invalid_chunk_events": missing_or_invalid_chunk_events[:20],
        "child_chunk_agent_ids": child_chunk_agent_ids,
        "persisted_agent_block_count": len(persisted_agent_blocks),
        "invalid_persisted_blocks": invalid_persisted_blocks[:20],
        "child_block_agent_ids": child_block_agent_ids,
        "orchestration_block_count": len(orchestration_blocks),
        "plan_summary_wrong_agent_blocks": plan_summary_wrong_agent_blocks[:10],
        "raw_agent_header_matches": raw_header_matches,
    }


def evaluate_p1_attribution(
    report: dict[str, Any],
    events: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> None:
    blocks = p1_content_blocks(report)
    agent_report = p1_agent_id_report(events, blocks)
    report["p1_agent_id_report"] = agent_report
    switch_agents = [
        agent_id
        for agent_id in report.get("agent_switch_to_agents", [])
        if agent_id in {"claude-code", "opencode-helper", "codex-helper"}
    ]
    file_names = {str(item.get("path", "")).rsplit("/", 1)[-1] for item in files}
    checks = report["checks"]
    checks["p1_attribution_two_sub_agent_switches"] = len(set(switch_agents)) >= 2
    checks["p1_attribution_sse_chunks_have_agent_id"] = (
        agent_report["chunk_event_count"] > 0
        and not agent_report["missing_or_invalid_chunk_events"]
    )
    checks["p1_attribution_sse_child_chunks_have_real_agent_id"] = (
        len(agent_report["child_chunk_agent_ids"]) >= 2
    )
    checks["p1_attribution_persisted_blocks_have_agent_id"] = (
        agent_report["persisted_agent_block_count"] > 0
        and not agent_report["invalid_persisted_blocks"]
    )
    checks["p1_attribution_persisted_child_blocks_segmented"] = (
        len(agent_report["child_block_agent_ids"]) >= 2
    )
    checks["p1_attribution_plan_summary_orchestrator"] = (
        agent_report["orchestration_block_count"] >= 1
        and not agent_report["plan_summary_wrong_agent_blocks"]
    )
    checks["p1_attribution_no_raw_agent_header_semantics"] = (
        not agent_report["raw_agent_header_matches"]
    )
    checks["p1_attribution_workspace_artifacts_created"] = {
        "p1-attribution-claude.md",
        "p1-attribution-opencode.md",
    }.issubset(file_names)
    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "p1_attribution_two_sub_agent_switches",
        "p1_attribution_sse_chunks_have_agent_id",
        "p1_attribution_sse_child_chunks_have_real_agent_id",
        "p1_attribution_persisted_blocks_have_agent_id",
        "p1_attribution_persisted_child_blocks_segmented",
        "p1_attribution_plan_summary_orchestrator",
        "p1_attribution_no_raw_agent_header_semantics",
        "p1_attribution_workspace_artifacts_created",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def evaluate_p1_workflow(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    files: list[dict[str, Any]],
) -> None:
    blocks = p1_content_blocks(report)
    workflow_blocks = [block for block in blocks if block.get("type") == "workflow"]
    report["workflow_blocks"] = workflow_blocks
    files_by_name = file_by_basename(files)
    workflow_item = files_by_name.get("p1-workflow.yaml")
    workflow_file_text = ""
    if workflow_item:
        workflow_file_text = read_workspace_file(
            client,
            str(report["conversation_id"]),
            headers,
            str(workflow_item["path"]),
        )
    report["workflow_file_preview"] = workflow_file_text[:4000]
    workflow_block = workflow_blocks[0] if workflow_blocks else {}
    definition = workflow_block.get("definition") if isinstance(workflow_block, dict) else {}
    nodes = workflow_block.get("nodes") if isinstance(workflow_block, dict) else []
    edges = workflow_block.get("edges") if isinstance(workflow_block, dict) else []
    final_summary = final_summary_from_report(report)
    checks = report["checks"]
    checks["p1_workflow_block_present"] = bool(workflow_blocks)
    checks["p1_workflow_block_has_agent_id"] = (
        workflow_block.get("agent_id") in {"claude-code", "opencode-helper", "codex-helper"}
    )
    checks["p1_workflow_block_has_name_path_format"] = (
        isinstance(workflow_block.get("name"), str)
        and bool(workflow_block.get("name"))
        and workflow_block.get("path") == "p1-workflow.yaml"
        and workflow_block.get("format") == "yaml"
    )
    checks["p1_workflow_block_has_definition_nodes_edges"] = (
        isinstance(definition, dict)
        and isinstance(nodes, list)
        and len(nodes) >= 3
        and isinstance(edges, list)
        and len(edges) >= 2
    )
    checks["p1_workflow_validation_passed"] = (
        workflow_block.get("validation_status") == "passed"
    )
    checks["p1_workflow_runtime_ready"] = (
        workflow_block.get("runtime_status") == "ready"
    )
    checks["p1_workflow_dry_run_not_supported"] = (
        workflow_block.get("dry_run_status") == "not_supported"
    )
    checks["p1_workflow_workspace_file_exists"] = workflow_item is not None
    checks["p1_workflow_summary_has_no_validation_failure"] = (
        "workflow_validation" not in final_summary.lower()
        or "workflow_validation passed" in final_summary.lower()
    )
    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "p1_workflow_block_present",
        "p1_workflow_block_has_agent_id",
        "p1_workflow_block_has_name_path_format",
        "p1_workflow_block_has_definition_nodes_edges",
        "p1_workflow_validation_passed",
        "p1_workflow_runtime_ready",
        "p1_workflow_dry_run_not_supported",
        "p1_workflow_workspace_file_exists",
        "p1_workflow_summary_has_no_validation_failure",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def evaluate_p1_workflow_runtime(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    files: list[dict[str, Any]],
) -> None:
    conv_id = str(report["conversation_id"])
    blocks = p1_content_blocks(report)
    workflow_blocks = [block for block in blocks if block.get("type") == "workflow"]
    report["workflow_runtime_blocks"] = workflow_blocks
    files_by_name = file_by_basename(files)
    workflow_item = files_by_name.get("p1-runtime-workflow.yaml")
    workflow_file_text = ""
    if workflow_item:
        workflow_file_text = read_workspace_file(
            client,
            conv_id,
            headers,
            str(workflow_item["path"]),
        )
    report["workflow_runtime_file_preview"] = workflow_file_text[:4000]
    workflow_block = workflow_blocks[0] if workflow_blocks else {}
    initial_runs = list_workflow_runs(
        client,
        conv_id,
        headers,
        "p1-runtime-workflow.yaml",
    )
    report["workflow_runtime_initial_runs"] = initial_runs
    last_run_id = str(workflow_block.get("last_run_id") or "")
    run_detail = get_workflow_run(client, conv_id, headers, last_run_id) if last_run_id else {}
    report["workflow_runtime_last_run_detail"] = run_detail
    extra_run = create_workflow_dry_run(
        client,
        conv_id,
        headers,
        "p1-runtime-workflow.yaml",
    )
    report["workflow_runtime_extra_run"] = extra_run
    after_runs = list_workflow_runs(
        client,
        conv_id,
        headers,
        "p1-runtime-workflow.yaml",
    )
    report["workflow_runtime_after_runs"] = after_runs
    health = get_workflow_health(client, conv_id, headers, "p1-runtime-workflow.yaml")
    report["workflow_runtime_health"] = health
    final_summary = final_summary_from_report(report).lower()
    checks = report["checks"]
    node_results = run_detail.get("node_results")
    extra_node_results = extra_run.get("node_results")
    checks["p1_workflow_runtime_block_present"] = bool(workflow_blocks)
    checks["p1_workflow_runtime_block_has_last_run_id"] = bool(last_run_id)
    checks["p1_workflow_runtime_statuses_passed"] = (
        workflow_block.get("validation_status") == "passed"
        and workflow_block.get("runtime_status") == "ready"
        and workflow_block.get("dry_run_status") == "passed"
        and workflow_block.get("health_status") == "passed"
    )
    checks["p1_workflow_runtime_workspace_file_exists"] = workflow_item is not None
    checks["p1_workflow_runtime_initial_run_present"] = bool(initial_runs)
    checks["p1_workflow_runtime_last_run_all_nodes_passed"] = (
        isinstance(node_results, list)
        and bool(node_results)
        and all(item.get("status") == "passed" for item in node_results)
    )
    checks["p1_workflow_runtime_extra_run_passed"] = (
        extra_run.get("status") == "passed"
        and isinstance(extra_node_results, list)
        and bool(extra_node_results)
        and all(item.get("status") == "passed" for item in extra_node_results)
    )
    checks["p1_workflow_runtime_history_increased"] = len(after_runs) > len(initial_runs)
    checks["p1_workflow_runtime_health_passed"] = (
        health.get("dry_run_status") == "passed"
        and health.get("health_status") == "passed"
        and isinstance(health.get("latest_run"), dict)
    )
    checks["p1_workflow_runtime_summary_mentions_dry_run"] = (
        "workflow dry-run" in final_summary and "passed" in final_summary
    )
    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "p1_workflow_runtime_block_present",
        "p1_workflow_runtime_block_has_last_run_id",
        "p1_workflow_runtime_statuses_passed",
        "p1_workflow_runtime_workspace_file_exists",
        "p1_workflow_runtime_initial_run_present",
        "p1_workflow_runtime_last_run_all_nodes_passed",
        "p1_workflow_runtime_extra_run_passed",
        "p1_workflow_runtime_history_increased",
        "p1_workflow_runtime_health_passed",
        "p1_workflow_runtime_summary_mentions_dry_run",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def evaluate_p1_review_thread(report: dict[str, Any]) -> None:
    run_detail = report.get("orchestrator_run_detail")
    tasks = run_detail.get("tasks") if isinstance(run_detail, dict) else []
    attempts = run_detail.get("attempts") if isinstance(run_detail, dict) else []
    events = run_detail.get("events") if isinstance(run_detail, dict) else []
    tasks = tasks if isinstance(tasks, list) else []
    attempts = attempts if isinstance(attempts, list) else []
    events = events if isinstance(events, list) else []
    task_types = [task.get("task_type") for task in tasks if isinstance(task, dict)]
    review_tasks = [
        task for task in tasks if isinstance(task, dict) and task.get("task_type") == "review"
    ]
    repair_tasks = [
        task for task in tasks if isinstance(task, dict) and task.get("task_type") == "repair"
    ]
    review_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict) and attempt.get("review_outcome")
    ]
    final_summary = final_summary_from_report(report)
    switched_agents = [
        agent_id
        for agent_id in report.get("agent_switch_to_agents", [])
        if isinstance(agent_id, str)
    ]
    checks = report["checks"]
    checks["p1_review_task_present"] = bool(review_tasks)
    checks["p1_repair_task_present"] = bool(repair_tasks)
    checks["p1_review_events_present"] = any(
        event.get("event_type") == "agent_review_completed" for event in events
    ) and any(
        event.get("event_type") == "agent_review_repair_scheduled" for event in events
    )
    checks["p1_review_outcome_needs_repair"] = any(
        attempt.get("review_outcome") == "needs_repair" for attempt in review_attempts
    )
    checks["p1_repair_uses_group_member"] = all(
        task.get("agent_id") in {"claude-code", "opencode-helper", "codex-helper"}
        for task in repair_tasks
    )
    checks["p1_dispatch_only_group_members"] = all(
        agent_id in {"claude-code", "opencode-helper", "codex-helper"}
        for agent_id in switched_agents
    )
    checks["p1_summary_includes_review_metadata"] = all(
        marker in final_summary
        for marker in ("review_of:", "handoff:", "review outcome: needs_repair")
    )
    report["review_thread"] = {
        "task_types": task_types,
        "review_tasks": review_tasks,
        "repair_tasks": repair_tasks,
        "review_attempts": review_attempts,
        "review_events": [
            event
            for event in events
            if event.get("event_type")
            in {"agent_review_completed", "agent_review_repair_scheduled"}
        ],
        "final_summary": final_summary,
    }
    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "p1_review_task_present",
        "p1_repair_task_present",
        "p1_review_events_present",
        "p1_review_outcome_needs_repair",
        "p1_repair_uses_group_member",
        "p1_dispatch_only_group_members",
        "p1_summary_includes_review_metadata",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def evaluate_p1_rich_artifacts(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
) -> None:
    conv_id = str(report["conversation_id"])
    blocks = p1_content_blocks(report)
    file_blocks = [block for block in blocks if block.get("type") == "file"]
    artifacts = get_workspace_artifacts(client, conv_id, headers)
    report["rich_artifact_file_blocks"] = file_blocks
    report["workspace_artifacts_api"] = artifacts
    required_kinds = {"document", "ppt", "image", "archive"}
    block_kinds = {str(block.get("artifact_kind")) for block in file_blocks}
    manifest_kinds = {str(item.get("artifact_kind")) for item in artifacts}
    manifest_by_path = {
        str(item.get("path")): item for item in artifacts if isinstance(item.get("path"), str)
    }
    aligned_blocks = []
    for block in file_blocks:
        path = block.get("path")
        manifest = manifest_by_path.get(path) if isinstance(path, str) else None
        aligned_blocks.append(
            bool(
                manifest
                and manifest.get("artifact_kind") == block.get("artifact_kind")
                and manifest.get("agent_id") == block.get("agent_id")
            )
        )
    checks = report["checks"]
    checks["p1_rich_artifacts_file_blocks_present"] = required_kinds.issubset(block_kinds)
    checks["p1_rich_artifacts_manifest_present"] = required_kinds.issubset(
        manifest_kinds
    )
    checks["p1_rich_artifacts_block_manifest_aligned"] = (
        bool(aligned_blocks) and all(aligned_blocks)
    )
    checks["p1_rich_artifacts_manifest_has_task_run_agent"] = all(
        item.get("agent_id") and item.get("task_id") and item.get("run_id")
        for item in artifacts
        if item.get("artifact_kind") in required_kinds
    )
    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "p1_rich_artifacts_file_blocks_present",
        "p1_rich_artifacts_manifest_present",
        "p1_rich_artifacts_block_manifest_aligned",
        "p1_rich_artifacts_manifest_has_task_run_agent",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def evaluate_p1_evaluation_repair(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
) -> None:
    conv_id = str(report["conversation_id"])
    run_detail = report.get("orchestrator_run_detail")
    attempts = run_detail.get("attempts") if isinstance(run_detail, dict) else []
    events = run_detail.get("events") if isinstance(run_detail, dict) else []
    attempts = attempts if isinstance(attempts, list) else []
    events = events if isinstance(events, list) else []
    event_attempts = _attempts_from_run_events(events)
    all_attempts = [*attempts, *event_attempts]
    artifacts = get_workspace_artifacts(client, conv_id, headers)
    report["workspace_artifacts_api"] = artifacts
    failed_attempts = [
        attempt
        for attempt in all_attempts
        if isinstance(attempt, dict)
        and any(
            isinstance(result, dict)
            and result.get("status") == "failed"
            and result.get("passed") is False
            for result in attempt.get("evaluation_results") or []
        )
    ]
    final_good_attempts = [
        attempt
        for attempt in all_attempts
        if isinstance(attempt, dict)
        and (attempt.get("final_state") or attempt.get("state"))
        in {"succeeded", "manual_review_required"}
    ]
    good_task_results = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("event_type") == "task_result"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("final_state") in {"succeeded", "manual_review_required"}
    ]
    manifest_false_passed = [
        item
        for item in artifacts
        if item.get("evaluation_status") == "passed"
        and any(
            isinstance(result, dict)
            and (
                result.get("status") == "failed"
                or result.get("evaluator") == "manual_review_required"
            )
            for result in item.get("evaluation_results") or []
        )
    ]
    checks = report["checks"]
    checks["p1_evaluation_failed_seen"] = bool(failed_attempts)
    checks["p1_evaluation_reflection_seen"] = any(
        event.get("event_type") == "reflection_created" for event in events
    )
    checks["p1_evaluation_repair_or_fallback_seen"] = (
        len(all_attempts) >= 2
        or any(
            event.get("event_type") in {"agent_review_repair_scheduled", "repair_dispatched"}
            for event in events
        )
    )
    checks["p1_evaluation_final_passed_or_manual"] = bool(
        final_good_attempts or good_task_results
    )
    checks["p1_evaluation_manifest_not_false_passed"] = not manifest_false_passed
    checks["p1_evaluation_manifest_status_present"] = any(
        item.get("evaluation_status") in {"failed", "passed", "manual_review_required"}
        for item in artifacts
    )
    report["evaluation_repair"] = {
        "failed_attempts": failed_attempts,
        "final_good_attempts": final_good_attempts,
        "good_task_results": good_task_results,
        "manifest_false_passed": manifest_false_passed,
    }
    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "p1_evaluation_failed_seen",
        "p1_evaluation_reflection_seen",
        "p1_evaluation_repair_or_fallback_seen",
        "p1_evaluation_final_passed_or_manual",
        "p1_evaluation_manifest_not_false_passed",
        "p1_evaluation_manifest_status_present",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def _attempts_from_run_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != "task_result":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        raw_attempts = payload.get("attempts")
        if not isinstance(raw_attempts, list):
            continue
        for attempt in raw_attempts:
            if isinstance(attempt, dict):
                attempts.append(attempt)
    return attempts


def evaluate_p1_agent_capability_profile(report: dict[str, Any]) -> None:
    profile = report.get("agent_capability_profile")
    profile_items = profile.get("items", []) if isinstance(profile, dict) else []
    profile_before = report.get("agent_capability_profile_before_followup")
    profile_before_items = (
        profile_before.get("items", []) if isinstance(profile_before, dict) else []
    )
    before_by_agent = {
        str(item.get("agent_id")): item
        for item in profile_before_items
        if isinstance(item, dict) and item.get("agent_id")
    }
    final_summary = final_summary_from_report(report).lower()
    target_text = visible_agent_text(p1_content_blocks(report)).lower()
    combined_text = f"{final_summary}\n{target_text}"
    agent_ids = {
        str(item.get("agent_id"))
        for item in profile_items
        if isinstance(item, dict) and item.get("agent_id")
    }
    run_detail = report.get("orchestrator_run_detail")
    tasks = run_detail.get("tasks", []) if isinstance(run_detail, dict) else []
    attempts = run_detail.get("attempts", []) if isinstance(run_detail, dict) else []
    followup_tasks = [
        task
        for task in tasks
        if isinstance(task, dict) and _is_capability_followup_task(task)
    ]
    followup_task_ids = {
        str(task.get("task_id"))
        for task in followup_tasks
        if task.get("task_id")
    }
    followup_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict)
        and str(attempt.get("task_id")) in followup_task_ids
        and attempt.get("state") not in {"pending", "skipped"}
    ]
    followup_task_agents = {
        str(task.get("agent_id")) for task in followup_tasks if task.get("agent_id")
    }
    followup_attempt_agents = {
        str(attempt.get("agent_id"))
        for attempt in followup_attempts
        if attempt.get("agent_id")
    }
    claude = before_by_agent.get("claude-code", {})
    opencode = before_by_agent.get("opencode-helper", {})
    checks: dict[str, bool] = {}
    checks["p1_agent_capability_profile_api_two_agents"] = len(agent_ids) >= 2
    checks["p1_agent_capability_seed_claude_failed"] = (
        int(claude.get("failure_count") or 0) >= 1
        and int(claude.get("evaluation_failed_count") or 0) >= 1
        and int(claude.get("success_count") or 0) == 0
    )
    checks["p1_agent_capability_seed_opencode_succeeded"] = (
        int(opencode.get("success_count") or 0) >= 1
    )
    checks["p1_agent_capability_memory_context_mentioned"] = (
        "agent capability profile from recent orchestrator runs" in combined_text
        or "capability profile" in combined_text
        or "能力画像" in combined_text
    )
    checks["p1_agent_capability_selection_basis_visible"] = (
        "recent success" in combined_text
        or "近期成功" in combined_text
        or "选择依据" in combined_text
    )
    checks["p1_agent_capability_followup_task_agent_opencode"] = (
        bool(followup_tasks) and followup_task_agents == {"opencode-helper"}
    )
    checks["p1_agent_capability_followup_attempt_agent_opencode"] = (
        bool(followup_attempts) and followup_attempt_agents == {"opencode-helper"}
    )
    checks["p1_agent_capability_followup_artifact_created"] = any(
        item.get("path") == "capability-followup.md"
        for item in report.get("workspace_files", [])
        if isinstance(item, dict)
    )
    report["agent_capability_profile_agent_ids"] = sorted(agent_ids)
    report["agent_capability_followup_task_agents"] = sorted(followup_task_agents)
    report["agent_capability_followup_attempt_agents"] = sorted(followup_attempt_agents)
    report["acceptance"] = {
        key: checks[key]
        for key in (
            "p1_agent_capability_profile_api_two_agents",
            "p1_agent_capability_seed_claude_failed",
            "p1_agent_capability_seed_opencode_succeeded",
            "p1_agent_capability_memory_context_mentioned",
            "p1_agent_capability_selection_basis_visible",
            "p1_agent_capability_followup_task_agent_opencode",
            "p1_agent_capability_followup_attempt_agent_opencode",
            "p1_agent_capability_followup_artifact_created",
        )
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def _is_capability_followup_task(task: dict[str, Any]) -> bool:
    text = "\n".join(
        str(task.get(key) or "") for key in ("title", "instruction", "expected_output")
    )
    return "capability-followup.md" in text


def run_p1_agent_capability_profile_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"{SCENARIO} Live E2E {int(started_at)}",
            "mode": "group",
            "agent_ids": P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS,
        },
    )
    conversation.raise_for_status()
    conv = conversation.json()
    conv_id = conv["id"]
    report["conversation"] = conv
    report["conversation_id"] = conv_id

    seed_sent, seed_events, seed_target = send_message_and_stream(
        client,
        headers,
        conv_id,
        content=P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT,
        target_agent_id="orchestrator",
        started_at=started_at,
    )
    report["seed_user_message_id"] = seed_sent["user_message"]["id"]
    report["seed_agent_message_id"] = seed_sent["agent_message"]["id"]
    report["seed_target_agent_message"] = seed_target
    report["seed_stream_event_count"] = len(seed_events)
    report["seed_agent_switch_to_agents"] = [
        event_data(event).get("to_agent")
        for event in seed_events
        if event.get("event") == "agent_switch"
    ]
    fetch_agent_capability_profile(client, headers, conv_id, report)
    report["agent_capability_profile_before_followup"] = report.get(
        "agent_capability_profile",
        {},
    )

    sent, events, target = send_message_and_stream(
        client,
        headers,
        conv_id,
        content=PROMPT,
        target_agent_id="orchestrator",
        started_at=started_at,
    )
    report["user_message_id"] = sent["user_message"]["id"]
    report["agent_message_id"] = sent["agent_message"]["id"]
    report["target_agent_message"] = target
    report["stream_event_count"] = len(events)
    report["agent_switch_to_agents"] = [
        event_data(event).get("to_agent")
        for event in events
        if event.get("event") == "agent_switch"
    ]
    report["checks"]["message_done"] = bool(target and target.get("status") == "done")
    fetch_orchestrator_run_detail(client, headers, conv_id, report)
    fetch_agent_capability_profile(client, headers, conv_id, report)
    fetch_workspace_evidence(client, headers, conv_id, report)
    report["content_block_types"] = [
        block.get("type") for block in p1_content_blocks(report)
    ]
    evaluate_p1_agent_capability_profile(report)


def run_p1_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    if P1_AGENT_CAPABILITY_PROFILE_SCENARIO:
        run_p1_agent_capability_profile_case(client, headers, report, started_at)
        return

    original_review_config: dict[str, Any] | None = None
    if P1_REVIEW_THREAD_SCENARIO:
        original_review_config = asyncio.run(
            _patch_orchestrator_review_config(["codex-helper"])
        )
        report["review_config_patch"] = {
            "review_config_patched": True,
            "original_config_summary": config_summary(original_review_config),
            "patched_config_summary": {
                **config_summary(original_review_config),
                "orchestrator_agent_review_enabled": True,
                "orchestrator_review_agent_ids": ["codex-helper"],
            },
        }

    try:
        events, files = p1_common_evidence(
            client,
            headers,
            report,
            started_at,
            title=f"{SCENARIO} Live E2E {int(started_at)}",
            agent_ids=AGENT_IDS,
        )
        if P1_ATTRIBUTION_SCENARIO:
            evaluate_p1_attribution(report, events, files)
        elif P1_WORKFLOW_SCENARIO:
            evaluate_p1_workflow(client, headers, report, files)
        elif P1_WORKFLOW_RUNTIME_SCENARIO:
            evaluate_p1_workflow_runtime(client, headers, report, files)
        elif P1_REVIEW_THREAD_SCENARIO:
            evaluate_p1_review_thread(report)
        elif P1_RICH_ARTIFACTS_SCENARIO:
            evaluate_p1_rich_artifacts(client, headers, report)
        elif P1_EVALUATION_REPAIR_SCENARIO:
            evaluate_p1_evaluation_repair(client, headers, report)
    finally:
        if original_review_config is not None:
            try:
                restore = asyncio.run(_restore_orchestrator_config(original_review_config))
            except Exception as exc:  # noqa: BLE001
                restore = {"restored": False, "error": str(exc)}
            report["review_config_restore"] = restore


def run_custom_agent_tools_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"Custom Agent Tools E2E {int(started_at)}",
            "mode": "group",
            "agent_ids": ["orchestrator", "opencode-helper"],
        },
    )
    conversation.raise_for_status()
    conv = conversation.json()
    conv_id = conv["id"]
    report["conversation"] = conv
    report["conversation_id"] = conv_id
    put_workspace_file(
        client,
        conv_id,
        headers,
        "notes.txt",
        "allowed-tools-live-sentinel",
    )

    _, create_events, create_target = send_message_and_stream(
        client,
        headers,
        conv_id,
        content=PROMPT,
        target_agent_id="orchestrator",
        started_at=started_at,
    )
    report["custom_agent_create_message"] = create_target
    create_tool_results = tool_results_by_name(create_events).get("create_custom_agent", [])
    create_payload = parse_tool_json(create_tool_results[-1] if create_tool_results else None)
    agent_payload = create_payload.get("agent") if isinstance(create_payload, dict) else None
    agent_id = agent_payload.get("id") if isinstance(agent_payload, dict) else None

    agents = client.get("/api/v1/agents", headers=headers)
    agents.raise_for_status()
    agent_items = agents.json().get("items", [])
    created_agent = next(
        (
            item
            for item in agent_items
            if item.get("id") == agent_id
            or str(item.get("name", "")).startswith("LiveReader-")
        ),
        None,
    )
    if not isinstance(agent_id, str) and created_agent:
        agent_id = created_agent.get("id")
    report["created_custom_agent"] = created_agent
    allowed_tools = (
        (created_agent.get("config") or {}).get("allowed_tools")
        if isinstance(created_agent, dict)
        else None
    )
    conversation_after_create = client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    conversation_after_create.raise_for_status()
    report["conversation_after_create"] = conversation_after_create.json()

    read_events: list[dict[str, Any]] = []
    write_events: list[dict[str, Any]] = []
    read_target: dict[str, Any] | None = None
    write_target: dict[str, Any] | None = None
    if isinstance(agent_id, str) and agent_id:
        _, read_events, read_target = send_message_and_stream(
            client,
            headers,
            conv_id,
            content=(
                "请使用 read_file 工具读取 notes.txt，并原样说出其中的 sentinel。"
            ),
            target_agent_id=agent_id,
            started_at=started_at,
        )
        _, write_events, write_target = send_message_and_stream(
            client,
            headers,
            conv_id,
            content=(
                "请尝试写入 forbidden.txt 或运行 bash。"
                "如果你没有相关工具，请直接说明无法执行。"
            ),
            target_agent_id=agent_id,
            started_at=started_at,
        )
    report["custom_agent_read_message"] = read_target
    report["custom_agent_write_message"] = write_target
    read_tool_calls = [
        event.get("data", {}).get("tool_name")
        for event in read_events
        if event.get("event") == "tool_call"
    ]
    write_tool_calls = [
        event.get("data", {}).get("tool_name")
        for event in write_events
        if event.get("event") == "tool_call"
    ]
    read_text = visible_agent_text((read_target or {}).get("content") or [])
    report["custom_agent_tool_calls"] = {
        "read": read_tool_calls,
        "write": write_tool_calls,
    }
    report["checks"]["custom_agent_created"] = isinstance(agent_id, str) and bool(agent_id)
    report["checks"]["custom_agent_allowed_tools_persisted"] = allowed_tools == ["read_file"]
    report["checks"]["custom_agent_added_to_group"] = (
        isinstance(agent_id, str)
        and agent_id in report["conversation_after_create"].get("agent_ids", [])
    )
    report["checks"]["custom_agent_read_file_available"] = (
        "read_file" in read_tool_calls or "allowed-tools-live-sentinel" in read_text
    )
    report["checks"]["custom_agent_unauthorized_tools_blocked"] = not any(
        tool_name in {"write_file", "bash"} for tool_name in write_tool_calls
    )
    acceptance = {
        key: report["checks"].get(key, False)
        for key in (
            "custom_agent_created",
            "custom_agent_allowed_tools_persisted",
            "custom_agent_added_to_group",
            "custom_agent_read_file_available",
            "custom_agent_unauthorized_tools_blocked",
        )
    }
    report["acceptance"] = {**acceptance, "passed": all(acceptance.values())}


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
        cleanup_previous_preview(client, headers, report)

        agents = client.get("/api/v1/agents", headers=headers)
        agents.raise_for_status()
        agent_items: list[dict[str, Any]] = agents.json().get("items", [])
        agent_ids = {item.get("id") for item in agent_items}
        missing_agents = [agent_id for agent_id in AGENT_IDS if agent_id not in agent_ids]
        report["checks"]["target_agents_present"] = not missing_agents
        if missing_agents:
            raise RuntimeError(f"missing target agents: {missing_agents}")
        if CUSTOM_AGENT_TOOLS_SCENARIO:
            run_custom_agent_tools_case(client, headers, report, started_at)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return
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
        if P1_SCENARIO:
            run_p1_case(client, headers, report, started_at)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return

        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json={
                "title": (
                    f"Orchestrator Fullstack Flow {int(started_at)}"
                    if FULLSTACK_SCENARIO
                    else f"Orchestrator Deployment Repair Flow {int(started_at)}"
                    if DEPLOYMENT_REPAIR_SCENARIO
                    else f"Orchestrator Deployment Flow {int(started_at)}"
                    if DEPLOYMENT_SCENARIO
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
        if DEPLOYMENT_REPAIR_SCENARIO:
            put_workspace_file(
                client,
                conv_id,
                headers,
                "index.html",
                (
                    "<!doctype html><html><head><link rel='stylesheet' href='styles.css'>"
                    "</head><body><h1>任务 代码 Diff 预览 按钮 移动</h1>"
                    "<button>Run</button><script src='app.js'></script></body></html>"
                ),
            )
            put_workspace_file(
                client,
                conv_id,
                headers,
                "styles.css",
                "body{font-family:sans-serif}button{padding:12px}",
            )
            put_workspace_file(
                client,
                conv_id,
                headers,
                "app.js",
                "document.querySelector('button').addEventListener('click',()=>{})",
            )
            put_workspace_file(
                client,
                conv_id,
                headers,
                "server.py",
                (
                    "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                    "class Handler(BaseHTTPRequestHandler):\n"
                    "    def do_GET(self):\n"
                    "        self.send_response(200)\n"
                    "        self.end_headers()\n"
                    "        self.wfile.write(b'ok')\n"
                    "HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()\n"
                ),
            )
            put_workspace_file(
                client,
                conv_id,
                headers,
                "Dockerfile",
                (
                    "FROM python:3.12-slim\n"
                    "WORKDIR /app\n"
                    "COPY missing-requirements.txt .\n"
                    "COPY server.py .\n"
                    "EXPOSE 8000\n"
                    "CMD [\"python\", \"server.py\"]\n"
                ),
            )

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
                raw_preview_url = preview_body.get("url")
                preview_url = normalize_http_url(raw_preview_url)
                report["preview_url"] = preview_url
                report["preview_url_raw"] = raw_preview_url
                report["checks"]["preview_uses_requested_8082"] = (
                    preview_body.get("port") == 8082
                    and ":8082/" in str(preview_url or "")
                )
                report["checks"]["platform_preview_auto_started"] = (
                    preview_body.get("entry_path") == entry["path"]
                    and preview_body.get("status") == "running"
                )
                if preview_url:
                    public = httpx.get(preview_url, timeout=10, trust_env=False)
                    report["checks"]["preview_8082_public_accessible"] = (
                        public.status_code == 200
                    )
                else:
                    report["checks"]["preview_8082_public_accessible"] = False
            else:
                report["preview_8082_error"] = preview.text
                report["checks"]["preview_uses_requested_8082"] = False
                report["checks"]["platform_preview_auto_started"] = False
                report["checks"]["preview_8082_public_accessible"] = False
            preview_checks = (
                "platform_preview_tool_called",
                "platform_preview_tool_succeeded",
                "platform_preview_auto_started",
                "preview_url_in_agent_message",
                "formal_preview_tool_called",
                "preview_uses_requested_8082",
                "preview_8082_public_accessible",
            )
            if not all(report["checks"].get(key, False) for key in preview_checks):
                report["bugs"].append(
                    {
                        "code": "platform_preview_not_auto_started",
                        "symptom": (
                            "The user requested deployment/preview, but the agent stream "
                            "did not complete a platform start_workspace_preview tool call."
                        ),
                        "checks": {
                            key: report["checks"].get(key, False)
                            for key in preview_checks
                        },
                        "preview_get_status_code": preview.status_code,
                        "preview_error": report.get("preview_8082_error"),
                    }
                )
            browser_checks = (
                "browser_verify_tool_called",
                "formal_browser_verify_tool_called",
                "browser_verify_tool_succeeded",
                "browser_verify_passed",
                "browser_no_console_errors",
                "browser_no_page_errors",
                "browser_no_failed_requests",
                "browser_mobile_no_horizontal_overflow",
                "browser_button_interaction_ok",
            )
            if not all(report["checks"].get(key, False) for key in browser_checks):
                report["bugs"].append(
                    {
                        "code": "browser_quality_gate_failed",
                        "symptom": (
                            "Platform preview started, but browser verification did not "
                            "pass all quality checks before deployment."
                        ),
                        "checks": {
                            key: report["checks"].get(key, False)
                            for key in browser_checks
                        },
                        "browser_issues": (
                            browser_report.get("issues") if browser_report else None
                        ),
                    }
                )

        if DEPLOYMENT_SCENARIO:
            content_blocks = (target or {}).get("content") or []
            deployment_tool_blocks = [
                block
                for block in content_blocks
                if block.get("type") == "tool_call"
                and block.get("tool_name") == "create_deployment"
            ]
            source_tool_blocks = [
                block
                for block in content_blocks
                if block.get("type") == "tool_call"
                and block.get("tool_name") == "package_workspace_source"
            ]
            deployment_status_blocks = [
                block
                for block in content_blocks
                if block.get("type") == "deployment_status"
            ]
            report["deployment_status_blocks"] = deployment_status_blocks
            report["checks"]["deployment_tool_called"] = bool(deployment_tool_blocks)
            report["checks"]["source_package_tool_called"] = bool(source_tool_blocks)
            report["checks"]["deployment_status_block_present"] = bool(
                deployment_status_blocks
            )
            deployments = client.get(
                f"/api/v1/workspaces/{conv_id}/deployments",
                headers=headers,
            )
            report["deployment_list_status_code"] = deployments.status_code
            deployments.raise_for_status()
            deployment_items = deployments.json().get("items", [])
            report["deployments"] = deployment_items
            static_items = [
                item
                for item in deployment_items
                if item.get("kind") == "static_site"
                and item.get("status") == "published"
            ]
            source_items = [
                item
                for item in deployment_items
                if item.get("kind") == "source_zip"
                and item.get("status") == "published"
            ]
            container_items = [
                item
                for item in deployment_items
                if item.get("kind") == "container"
                and item.get("status") == "published"
            ]
            failed_container_items = [
                item
                for item in deployment_items
                if item.get("kind") == "container" and item.get("status") == "failed"
            ]
            report["checks"]["static_site_deployment_published"] = bool(static_items)
            report["checks"]["container_deployment_published"] = bool(container_items)
            report["checks"]["source_zip_deployment_published"] = bool(source_items)
            report["failed_container_deployments"] = failed_container_items
            if static_items:
                static_url = static_items[0].get("url")
                report["static_site_deployment_url"] = static_url
                if isinstance(static_url, str) and static_url.startswith("http"):
                    static_response = httpx.get(
                        static_url,
                        timeout=10,
                        trust_env=False,
                    )
                    report["checks"]["static_site_url_200"] = (
                        static_response.status_code == 200
                    )
                else:
                    report["checks"]["static_site_url_200"] = False
            else:
                report["checks"]["static_site_url_200"] = False
            report["checks"]["container_url_200"] = False
            report["checks"]["container_health_ok"] = False
            if container_items:
                container_url = container_items[0].get("url")
                healthcheck_url = container_items[0].get("healthcheck_url")
                report["container_deployment_url"] = container_url
                report["container_healthcheck_url"] = healthcheck_url
                if isinstance(container_url, str) and container_url.startswith("http"):
                    container_response = httpx.get(
                        container_url,
                        timeout=10,
                        trust_env=False,
                    )
                    report["checks"]["container_url_200"] = (
                        container_response.status_code == 200
                    )
                if isinstance(healthcheck_url, str) and healthcheck_url.startswith("http"):
                    health_response = httpx.get(
                        healthcheck_url,
                        timeout=10,
                        trust_env=False,
                    )
                    report["checks"]["container_health_ok"] = (
                        health_response.status_code == 200
                    )
            report["checks"]["source_zip_downloaded"] = False
            report["checks"]["source_zip_excludes_sensitive_paths"] = False
            if source_items:
                download_url = source_items[0].get("download_url")
                if isinstance(download_url, str) and download_url:
                    download = client.get(download_url, headers=headers)
                    report["source_zip_download_status_code"] = download.status_code
                    if download.status_code == 200:
                        report["checks"]["source_zip_downloaded"] = True
                        with zipfile.ZipFile(BytesIO(download.content)) as archive:
                            archive_names = archive.namelist()
                        report["source_zip_entries"] = archive_names
                        report["checks"]["source_zip_excludes_sensitive_paths"] = all(
                            not any(
                                part in SOURCE_EXPORT_EXCLUDED_PARTS
                                for part in Path(name).parts
                            )
                            for name in archive_names
                        )
            if DEPLOYMENT_REPAIR_SCENARIO:
                run_events = (
                    report.get("orchestrator_run_detail", {}).get("events", [])
                    if isinstance(report.get("orchestrator_run_detail"), dict)
                    else []
                )
                deployment_reflections = [
                    event
                    for event in run_events
                    if event.get("event_type") == "reflection_created"
                    and (
                        ((event.get("payload") or {}).get("reflection") or {}).get(
                            "failure_category"
                        )
                        == "deployment_health_failed"
                    )
                ]
                container_tool_blocks = [
                    block
                    for block in deployment_tool_blocks
                    if (block.get("arguments") or {}).get("kind") == "container"
                ]
                report["deployment_repair_reflections"] = deployment_reflections
                report["checks"]["deployment_repair_initial_failure_seen"] = bool(
                    failed_container_items
                )
                report["checks"]["deployment_repair_reflection_created"] = bool(
                    deployment_reflections
                )
                report["checks"]["deployment_repair_redeploy_called"] = (
                    len(container_tool_blocks) >= 2
                )
            deployment_checks = (
                "deployment_tool_called",
                "source_package_tool_called",
                "deployment_status_block_present",
                "static_site_deployment_published",
                "static_site_url_200",
                "source_zip_deployment_published",
                "source_zip_downloaded",
                "source_zip_excludes_sensitive_paths",
                "container_deployment_published",
                "container_url_200",
                "container_health_ok",
            )
            if DEPLOYMENT_REPAIR_SCENARIO:
                deployment_checks = (
                    *deployment_checks,
                    "deployment_repair_initial_failure_seen",
                    "deployment_repair_reflection_created",
                    "deployment_repair_redeploy_called",
                )
            if not all(report["checks"].get(key, False) for key in deployment_checks):
                report["bugs"].append(
                    {
                        "code": "deployment_release_flow_failed",
                        "symptom": (
                            "Deployment Case 3 did not complete static publish, "
                            "source zip export, status card, or container deployment."
                        ),
                        "checks": {
                            key: report["checks"].get(key, False)
                            for key in deployment_checks
                        },
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
        elif DEPLOYMENT_SCENARIO:
            hard_checks.update(
                {
                    "deployment_tool_called": report["checks"].get(
                        "deployment_tool_called",
                        False,
                    ),
                    "source_package_tool_called": report["checks"].get(
                        "source_package_tool_called",
                        False,
                    ),
                    "deployment_status_block_present": report["checks"].get(
                        "deployment_status_block_present",
                        False,
                    ),
                    "static_site_deployment_published": report["checks"].get(
                        "static_site_deployment_published",
                        False,
                    ),
                    "static_site_url_200": report["checks"].get(
                        "static_site_url_200",
                        False,
                    ),
                    "source_zip_deployment_published": report["checks"].get(
                        "source_zip_deployment_published",
                        False,
                    ),
                    "source_zip_downloaded": report["checks"].get(
                        "source_zip_downloaded",
                        False,
                    ),
                    "source_zip_excludes_sensitive_paths": report["checks"].get(
                        "source_zip_excludes_sensitive_paths",
                        False,
                    ),
                    "container_deployment_published": report["checks"].get(
                        "container_deployment_published",
                        False,
                    ),
                    "container_url_200": report["checks"].get(
                        "container_url_200",
                        False,
                    ),
                    "container_health_ok": report["checks"].get(
                        "container_health_ok",
                        False,
                    ),
                }
            )
            if DEPLOYMENT_REPAIR_SCENARIO:
                hard_checks.update(
                    {
                        "deployment_repair_initial_failure_seen": report["checks"].get(
                            "deployment_repair_initial_failure_seen",
                            False,
                        ),
                        "deployment_repair_reflection_created": report["checks"].get(
                            "deployment_repair_reflection_created",
                            False,
                        ),
                        "deployment_repair_redeploy_called": report["checks"].get(
                            "deployment_repair_redeploy_called",
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
