"""Run the deployed Orchestrator 8082 demo flow and write a JSON report.

This script intentionally uses the same HTTP API surface as the deployed frontend.
It is opt-in and intended for manual/live verification, not default CI.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import stat
import time
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from .config import load_settings

SETTINGS = load_settings()
BASE_URL = SETTINGS.base_url
USERNAME = SETTINGS.username
PASSWORD = SETTINGS.password
SCENARIO = SETTINGS.scenario
P1_ATTRIBUTION_SCENARIO = SCENARIO == "p1_attribution"
P1_WORKFLOW_SCENARIO = SCENARIO == "p1_workflow"
P1_WORKFLOW_RUNTIME_SCENARIO = SCENARIO == "p1_workflow_runtime"
P1_REVIEW_THREAD_SCENARIO = SCENARIO == "p1_review_thread_repair"
P1_RICH_ARTIFACTS_SCENARIO = SCENARIO == "p1_rich_artifacts"
P1_EVALUATION_REPAIR_SCENARIO = SCENARIO == "p1_evaluation_repair"
P1_AGENT_CAPABILITY_PROFILE_SCENARIO = SCENARIO == "p1_agent_capability_profile"
P2_AGENT_CAPABILITY_PROFILE_V2_SCENARIO = (
    SCENARIO == "p2_agent_capability_profile_v2"
)
ARCHITECTED_FRONTEND_GROUP_CHAT_SCENARIO = (
    SCENARIO == "architected_frontend_group_chat_repair"
)
GENERIC_GROUP_PROCESS_SCENARIOS = {
    "group_process_document_strategy",
    "group_process_data_analysis",
    "group_process_workflow_delivery",
    "group_process_failure_readable",
}
GENERIC_GROUP_PROCESS_SCENARIO = SCENARIO in GENERIC_GROUP_PROCESS_SCENARIOS
GROUP_PROCESS_FRONTEND_PREVIEW_SCENARIO = SCENARIO == "group_process_frontend_preview"
AGENT_FALLBACK_MATRIX_SCENARIO = SCENARIO == "agent_fallback_matrix"
CONTEXT_FOLLOWUP_SCENARIO = SCENARIO == "orchestrator_context_followup_repair"
PRESENTATION_COLLAPSE_SCENARIO = SCENARIO == "presentation_collapse_markers_smoke"
GROUP_DIALOGUE_DEBATE_SCENARIO = SCENARIO == "group_dialogue_debate_no_artifacts"
GROUP_SUBSTANTIVE_OUTPUT_MATRIX_SCENARIO = SCENARIO == "group_substantive_output_matrix"
AGENT_TURN_TAKING_DIALOGUE_SCENARIO = SCENARIO == "agent_turn_taking_dialogue_repair"
AGENT_TURN_TAKING_MATRIX_SCENARIO = SCENARIO == "agent_turn_taking_matrix"
MANUAL_TWO_AGENT_TURN_TAKING_SCENARIO = SCENARIO == "manual_two_agent_turn_taking"
COMMAND_FULFILLMENT_SCENARIO = (
    SCENARIO == "command_fulfillment_cyberpunk_group_deploy"
)
COMMAND_FULFILLMENT_FLOW_SCENARIO = (
    COMMAND_FULFILLMENT_SCENARIO or CONTEXT_FOLLOWUP_SCENARIO
)
P1_SCENARIO = (
    P1_ATTRIBUTION_SCENARIO
    or P1_WORKFLOW_SCENARIO
    or P1_WORKFLOW_RUNTIME_SCENARIO
    or P1_REVIEW_THREAD_SCENARIO
    or P1_RICH_ARTIFACTS_SCENARIO
    or P1_EVALUATION_REPAIR_SCENARIO
    or P1_AGENT_CAPABILITY_PROFILE_SCENARIO
)
P2_SCENARIO = P2_AGENT_CAPABILITY_PROFILE_V2_SCENARIO
FULLSTACK_SCENARIO = SCENARIO == "fullstack"
DEPLOYMENT_REPAIR_SCENARIO = SCENARIO == "deployment_repair"
CUSTOM_AGENT_TOOLS_SCENARIO = SCENARIO == "custom_agent_tools"
DEPLOYMENT_SCENARIO = SCENARIO in {"deployment", "deployment_repair"}
EXPECT_CONTAINER_STATUS = SETTINGS.expect_container_status
CONTAINER_TERMINAL_STATUSES = {"published", "failed", "stopped", "not_supported"}
CONTAINER_POLL_TIMEOUT_SECONDS = SETTINGS.container_poll_timeout_seconds
CONTAINER_POLL_INTERVAL_SECONDS = SETTINGS.container_poll_interval_seconds
AGENT_FALLBACK_E2E_FAIL_RUNTIME = "/tmp/agenthub-e2e-fail-runtime.py"  # noqa: S108
AGENT_FALLBACK_E2E_WRITE_RUNTIME = "/tmp/agenthub-e2e-write-runtime.py"  # noqa: S108
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
DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DOCUMENT_STRATEGY_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_document_strategy_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DATA_ANALYSIS_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_data_analysis_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_WORKFLOW_DELIVERY_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_workflow_delivery_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FAILURE_READABLE_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_failure_readable_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_frontend_preview_sse.jsonl"  # noqa: S108
)
DEFAULT_AGENT_FALLBACK_MATRIX_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_fallback_matrix_sse.jsonl"  # noqa: S108
)
DEFAULT_COMMAND_FULFILLMENT_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_command_fulfillment_sse.jsonl"  # noqa: S108
)
DEFAULT_CONTEXT_FOLLOWUP_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_context_followup_sse.jsonl"  # noqa: S108
)
DEFAULT_PRESENTATION_MARKERS_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_presentation_markers_sse.jsonl"  # noqa: S108
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
DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p2_agent_capability_profile_v2_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DOCUMENT_STRATEGY_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_document_strategy_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DATA_ANALYSIS_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_data_analysis_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_WORKFLOW_DELIVERY_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_workflow_delivery_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FAILURE_READABLE_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_failure_readable_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_frontend_preview_report.json"  # noqa: S108
)
DEFAULT_AGENT_FALLBACK_MATRIX_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_fallback_matrix_report.json"  # noqa: S108
)
DEFAULT_COMMAND_FULFILLMENT_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_command_fulfillment_report.json"  # noqa: S108
)
DEFAULT_CONTEXT_FOLLOWUP_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_context_followup_report.json"  # noqa: S108
)
DEFAULT_PRESENTATION_MARKERS_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_presentation_markers_report.json"  # noqa: S108
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
DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_frontend_preview_browser.json"  # noqa: S108
)
DEFAULT_COMMAND_FULFILLMENT_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_command_fulfillment_browser.json"  # noqa: S108
)
DEFAULT_CONTEXT_FOLLOWUP_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_context_followup_browser.json"  # noqa: S108
)
DEFAULT_PRESENTATION_MARKERS_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_presentation_markers_browser.json"  # noqa: S108
)
SSE_PATH = SETTINGS.sse_path
REPORT_PATH = SETTINGS.report_path
BROWSER_REPORT_PATH = SETTINGS.browser_report_path
FRONTEND_UI_SMOKE_ENABLED = os.getenv("AGENTHUB_E2E_FRONTEND_UI_SMOKE", "").lower() in {
    "1",
    "true",
    "yes",
}
FRONTEND_BASE_URL = os.getenv(
    "AGENTHUB_E2E_FRONTEND_BASE_URL",
    "http://154.44.25.94:1573",
)
FRONTEND_HANDOFF_REPORT_PATH = Path(
    os.getenv(
        "AGENTHUB_E2E_FRONTEND_HANDOFF_REPORT_PATH",
        "/tmp/agenthub_orchestrator_frontend_handoff_report.json",  # noqa: S108
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
P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT = (
    "@orchestrator 请进行 Agent Capability Profile v2 跨 conversation 规划验收。"
    "当前请求不点名任何执行 Agent；请根据 user-scope v2 capability profile 和 "
    "user preference memory，自主选择近期成功的文档 Agent，创建 "
    "p2-capability-v2-followup.md，内容必须包含 "
    "CAPABILITY_PROFILE_V2_FOLLOWUP_SENTINEL。最终总结必须明确出现 "
    "Agent capability profile v2 from recent user Orchestrator runs、"
    "User preference memory from recent Orchestrator runs、user-scope、"
    "recent success、选择依据、被选择 agent id。只规划一个逻辑文档任务，"
    "禁止新增 review 或 verification task；不要先让画像较弱的 Agent 尝试再 fallback，"
    "唯一 task 及其所有实际 attempt 都应由 v2 画像显示近期成功的 Agent 执行。"
    "不要预览、不要部署。"
)
GROUP_PROCESS_DOCUMENT_STRATEGY_PROMPT = (
    "@orchestrator 请进行通用真实 Agent 群聊与流式 process 验收，任务类型是文档策略，"
    "不要预览、不要部署。请使用 Claude Code 和 OpenCode Helper 两个可用 Agent "
    "按真实分工完成：先由一个 Agent 创建 strategy-architecture.md，说明目标、"
    "结构和分工；再由另一个 Agent 创建 customer-journey.md，写出用户旅程和关键"
    "触点；最后由可用 Agent 创建 risk-review.md，写出风险清单、验证建议和整合"
    "意见。每个参与 Agent 都要在自己的独立消息中展示公开过程，最终由 Orchestrator "
    "总结三份产物。"
)
GROUP_PROCESS_DATA_ANALYSIS_PROMPT = (
    "@orchestrator 请进行通用真实 Agent 群聊与流式 process 验收，任务类型是数据分析，"
    "不要预览、不要部署。请使用 Claude Code 和 OpenCode Helper 两个可用 Agent "
    "按真实分工完成：一个 Agent 创建 data-plan.md，定义分析口径和字段；一个 Agent "
    "创建 sample-metrics.csv，至少 6 行业务指标样本；一个 Agent 创建 "
    "analysis-report.md，基于 CSV 给出趋势、异常点和下一步建议。最终由 Orchestrator "
    "总结数据产物、负责 Agent 和验证结果。"
)
GROUP_PROCESS_WORKFLOW_DELIVERY_PROMPT = (
    "@orchestrator 请进行通用真实 Agent 群聊与流式 process 验收，任务类型是 workflow "
    "交付，不要预览、不要部署。请使用 Claude Code 和 OpenCode Helper 两个可用 "
    "Agent 按真实分工完成：一个 Agent 创建 workflow-plan.md，说明 workflow 目标和"
    "节点；一个 Agent 创建 "
    "group-process-workflow.yaml，并在回复中输出同一份合法 workflow-yaml fenced block。"
    "Workflow 必须包含 version、name、nodes、edges，name 为 Group Process Workflow "
    "E2E。nodes 包含 start(trigger)、set_context(task，config.action=set_context，"
    "config.values.group.status=ready)、check(assert，config.equals.group.status=ready)、"
    "done(end)。edges 使用 source/target 依次连接 start -> set_context -> check -> done。"
    "另一个可用 Agent 创建 workflow-review.md，检查 YAML、dry-run 风险和验收点。"
    "最终总结必须确认 workflow validation 与 dry-run 状态。"
)
GROUP_PROCESS_FAILURE_READABLE_PROMPT = (
    "@orchestrator 请进行通用真实 Agent 群聊与流式 process 验收，任务类型是可读失败处理，"
    "不要预览、不要部署。请使用 Claude Code 和 OpenCode Helper 两个可用 Agent "
    "按真实分工完成：一个 Agent 创建 failure-plan.md，说明为什么 workspace 只能写"
    "相对安全路径；另一个 Agent 尝试执行一个应被平台安全策略拒绝的动作：创建 "
    "../outside-workspace.txt 或写入 workspace 外部路径。"
    "如果平台拒绝或 Agent 无法完成，必须用用户可读中文说明哪个阶段失败、原因是安全"
    "路径限制、后续是否可重试；不要输出 raw stderr、stack trace、call id 或内部 prompt。"
    "最终由 Orchestrator 总结可完成产物和失败归属。"
)
AGENT_FALLBACK_MATRIX_PROMPT = (
    "@orchestrator 请执行通用 Agent fallback 验收任务。首选 Agent 可能不可用；"
    "如果它失败，请自动调配其他可用 Agent 继续，创建指定 markdown 文件，并在最终总结"
    "说明 fallback 归属。不要预览、不要部署。"
)
COMMAND_FULFILLMENT_PROMPT = (
    "@orchestrator 我要做一个网站，主题是赛博朋克风，先生成一份文档，"
    "然后交由两个智能体并行开发工作，包含代码产物、Diff、按钮交互和移动端适配，"
    "最后再进行审阅，最后部署在端口8082，并完成浏览器级质量验收。"
)
PRESENTATION_COLLAPSE_PROMPT = (
    "@orchestrator 请让一个可用 Agent 创建 collapse-marker.txt，"
    "内容包含 PRESENTATION_COLLAPSE_SENTINEL；然后由 Orchestrator 用自然语言总结。"
    "这个任务用于验证 presentation marker，请保留成员独立消息、公开执行过程和最终回答。"
)
GROUP_DIALOGUE_DEBATE_PROMPT = (
    "@orchestrator 组织群组内两个智能体开展辩论，论题是AI的快速发展对人类社会"
    "利大于弊还是弊大于利？不需要生成文件直接以对话的形式输出，注意是"
    "对话场景而不是书面书写。"
)
AGENT_TURN_TAKING_DIALOGUE_PROMPT = (
    "@orchestrator 组织群组内两个智能体开展辩论，论题是AI的快速发展对人类社会"
    "利大于弊还是弊大于利？不需要生成文件直接以对话的形式输出，注意是对话场景。"
    "由 Claude Code 先开始，一人一句回应对方，结束发言后可以 @另一个agent。"
)
MANUAL_TWO_AGENT_TURN_TAKING_PROMPT = (
    "组织群组内两个智能体开展辩论，论题是AI的快速发展对人类社会利大于弊还是弊大于利？"
    "不需要生成文件直接以对话的形式输出，注意是对话场景而不是书面书写。"
    "由Claude code先开始，一人一句开始辩论不要直接输出全部对话，"
    "要针对另一个AI的输出展开辩论，结束发言后使用@其他agent让他回复进行辩论 @claude-code"
)
GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT = (
    "@orchestrator 请进行通用子 Agent 实质输出验收，不需要生成文件。"
    "组织两个智能体围绕“AI 助手进入中小企业日常运营”做圆桌讨论："
    "一个成员给出支持采用的观点、理由和落地建议，另一个成员从风险、"
    "成本和治理角度提出质疑与替代方案。请直接以群聊发言形式输出。"
)

GROUP_SUBSTANTIVE_OUTPUT_MATRIX_CASES = (
    {
        "name": "debate_no_artifacts",
        "prompt": GROUP_DIALOGUE_DEBATE_PROMPT,
    },
    {
        "name": "roundtable_no_artifacts",
        "prompt": GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT,
    },
    {
        "name": "roleplay_dialogue",
        "prompt": (
            "@orchestrator 不需要生成文件，请组织两个智能体做角色扮演对话场景："
            "一位扮演产品经理，一位扮演安全负责人，讨论是否在客服系统接入 AI。"
            "请直接用群聊对话形式输出，每个角色都要给出自己的判断和理由。"
        ),
    },
    {
        "name": "strategy_brainstorm",
        "prompt": (
            "@orchestrator 不需要生成文件，请让两个智能体进行头脑风暴："
            "为 AgentHub 的新用户 onboarding 提出策略。每个智能体必须直接给出"
            "具体建议、理由和风险，不要写报告。"
        ),
    },
    {
        "name": "data_analysis_no_file",
        "prompt": (
            "@orchestrator 不需要生成文件，请让两个智能体分析这组数据："
            "渠道 A 转化率 12%、渠道 B 转化率 7%、渠道 C 转化率 15%，预算分别为"
            " 30/20/10 万。请直接在群聊里给出结论、依据和下一步建议。"
        ),
    },
    {
        "name": "code_artifact_with_summary",
        "prompt": (
            "@orchestrator 请让两个智能体协作完成一个很小的静态前端组件："
            "第一个智能体创建 index.html、styles.css、app.js，内容是一个可点击"
            "切换状态的任务卡片；第二个智能体检查产物并总结变更。每个智能体都要"
            "在自己的消息里给出阶段总结。"
        ),
    },
    {
        "name": "review_requires_gaps",
        "prompt": (
            "@orchestrator 请让两个智能体协作完成文档审阅：第一个智能体创建"
            "planning.md，说明 AgentHub 新手引导方案；第二个智能体必须审阅该文档，"
            "指出 pass/fail、gaps、风险和改进建议，并生成 review.md。"
        ),
    },
)

PROMPT = SETTINGS.prompt_override or (
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
    else P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
    if P2_AGENT_CAPABILITY_PROFILE_V2_SCENARIO
    else GROUP_PROCESS_DOCUMENT_STRATEGY_PROMPT
    if SCENARIO == "group_process_document_strategy"
    else GROUP_PROCESS_DATA_ANALYSIS_PROMPT
    if SCENARIO == "group_process_data_analysis"
    else GROUP_PROCESS_WORKFLOW_DELIVERY_PROMPT
    if SCENARIO == "group_process_workflow_delivery"
    else GROUP_PROCESS_FAILURE_READABLE_PROMPT
    if SCENARIO == "group_process_failure_readable"
    else AGENT_FALLBACK_MATRIX_PROMPT
    if AGENT_FALLBACK_MATRIX_SCENARIO
    else COMMAND_FULFILLMENT_PROMPT
    if COMMAND_FULFILLMENT_FLOW_SCENARIO
    else PRESENTATION_COLLAPSE_PROMPT
    if PRESENTATION_COLLAPSE_SCENARIO
    else GROUP_DIALOGUE_DEBATE_PROMPT
    if GROUP_DIALOGUE_DEBATE_SCENARIO
    else AGENT_TURN_TAKING_DIALOGUE_PROMPT
    if AGENT_TURN_TAKING_DIALOGUE_SCENARIO
    else MANUAL_TWO_AGENT_TURN_TAKING_PROMPT
    if MANUAL_TWO_AGENT_TURN_TAKING_SCENARIO
    else GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT
    if GROUP_SUBSTANTIVE_OUTPUT_MATRIX_SCENARIO or AGENT_TURN_TAKING_MATRIX_SCENARIO
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
    )
)
AGENT_IDS = ["orchestrator", "claude-code", "opencode-helper", "codex-helper"]
BUILTIN_SUB_AGENT_IDS = ("claude-code", "opencode-helper", "codex-helper")
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
GENERIC_GROUP_PROCESS_CASES: dict[str, dict[str, Any]] = {
    "group_process_document_strategy": {
        "required_files": {
            "strategy-architecture.md",
            "customer-journey.md",
            "risk-review.md",
        },
        "min_child_messages": 2,
        "required_child_agents": {"claude-code", "opencode-helper"},
    },
    "group_process_data_analysis": {
        "required_files": {
            "data-plan.md",
            "sample-metrics.csv",
            "analysis-report.md",
        },
        "min_child_messages": 2,
        "required_child_agents": {"claude-code", "opencode-helper"},
    },
    "group_process_workflow_delivery": {
        "required_files": {
            "workflow-plan.md",
            "group-process-workflow.yaml",
            "workflow-review.md",
        },
        "min_child_messages": 2,
        "required_child_agents": {"claude-code", "opencode-helper"},
        "require_workflow": True,
    },
    "group_process_failure_readable": {
        "required_files": {"failure-plan.md"},
        "min_child_messages": 2,
        "required_child_agents": {"claude-code", "opencode-helper"},
        "allow_child_error": True,
        "require_failure_text": True,
    },
}
AGENT_FALLBACK_MATRIX_CASES: tuple[dict[str, Any], ...] = (
    {
        "name": "agent_fallback_claude_unavailable",
        "target_agent_id": "claude-code",
        "fallback_agent_id": "opencode-helper",
        "artifact_path": "fallback-claude.md",
        "sub_agent_config_overrides": {
            "claude-code": {
                "runtime": "cli",
                "command": ["python3", AGENT_FALLBACK_E2E_FAIL_RUNTIME],
            },
            "opencode-helper": {
                "command": ["python3", AGENT_FALLBACK_E2E_WRITE_RUNTIME],
                "jsonl": False,
            },
        },
    },
    {
        "name": "agent_fallback_opencode_unavailable",
        "target_agent_id": "opencode-helper",
        "fallback_agent_id": "claude-code",
        "artifact_path": "fallback-opencode.md",
        "sub_agent_config_overrides": {
            "opencode-helper": {"command": "/tmp/agenthub-missing-opencode-cli"},  # noqa: S108
        },
    },
    {
        "name": "agent_fallback_codex_unavailable",
        "target_agent_id": "codex-helper",
        "fallback_agent_id": "claude-code",
        "artifact_path": "fallback-codex.md",
        "sub_agent_config_overrides": {
            "codex-helper": {"command": ["python3", AGENT_FALLBACK_E2E_FAIL_RUNTIME]},
        },
    },
)
FORBIDDEN_VISIBLE_TRACE_TERMS = (
    "ReAct step",
    "Observation:",
    "Action:",
    "Tools:",
    "call_",
    "Traceback (most recent call last)",
    "Permission denied",
    "[Errno",
    "/root/.agenthub",
    "claude-auth",
    ".claude.json",
    "/workspaces/",
    "OpenAI Codex",
    "workdir:",
    "approval:",
    "sandbox:",
    "UnknownError",
    "external_runtime_error",
)
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


def get_deployment_detail(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    deployment_id: str,
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/workspaces/{conv_id}/deployments/{deployment_id}",
        headers=headers,
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def wait_for_deployment_terminal(
    client: httpx.Client,
    conv_id: str,
    headers: dict[str, str],
    deployment: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    deployment_id = deployment.get("id")
    if not isinstance(deployment_id, str) or not deployment_id:
        return deployment, 0.0
    started = time.monotonic()
    current = deployment
    while current.get("status") not in CONTAINER_TERMINAL_STATUSES:
        elapsed = time.monotonic() - started
        if elapsed >= CONTAINER_POLL_TIMEOUT_SECONDS:
            return current, elapsed
        time.sleep(CONTAINER_POLL_INTERVAL_SECONDS)
        current = get_deployment_detail(client, conv_id, headers, deployment_id)
    return current, time.monotonic() - started


def is_url_unavailable(url: Any) -> bool:
    if not isinstance(url, str) or not url.startswith("http"):
        return False
    try:
        response = httpx.get(url, timeout=10, trust_env=False)
    except httpx.HTTPError:
        return True
    return response.status_code in {404, 410}


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
    result = await _restore_builtin_agent_config("orchestrator", config)
    return {
        "restored": result["restored"],
        "restored_config_summary": config_summary(config),
    }


async def _restore_builtin_agent_config(
    agent_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    from app.core.database import SessionFactory, engine
    from app.models.agent import Agent

    async with SessionFactory() as db:
        agent = await db.get(Agent, agent_id)
        if agent is None:
            raise RuntimeError(f"{agent_id} agent not found")
        agent.config = dict(config)
        await db.commit()
    await engine.dispose()
    return {"restored": True, "agent_id": agent_id}


async def _patch_builtin_agent_config(
    agent_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    from app.core.database import SessionFactory, engine
    from app.models.agent import Agent

    async with SessionFactory() as db:
        agent = await db.get(Agent, agent_id)
        if agent is None:
            raise RuntimeError(f"{agent_id} agent not found")
        original_config = dict(agent.config or {})
        agent.config = {**original_config, **updates}
        await db.commit()
    await engine.dispose()
    return original_config


async def _patch_agent_provider(agent_id: str, provider: str) -> str:
    from app.core.database import SessionFactory, engine
    from app.models.agent import Agent

    async with SessionFactory() as db:
        agent = await db.get(Agent, agent_id)
        if agent is None:
            raise RuntimeError(f"{agent_id} agent not found")
        original_provider = agent.provider
        agent.provider = provider
        await db.commit()
    await engine.dispose()
    return original_provider


async def _restore_agent_provider(agent_id: str, provider: str) -> dict[str, Any]:
    from app.core.database import SessionFactory, engine
    from app.models.agent import Agent

    async with SessionFactory() as db:
        agent = await db.get(Agent, agent_id)
        if agent is None:
            raise RuntimeError(f"{agent_id} agent not found")
        agent.provider = provider
        await db.commit()
    await engine.dispose()
    return {"restored": True, "agent_id": agent_id, "provider": provider}


async def _patch_orchestrator_static_task_config(
    *,
    target_agent_id: str,
    fallback_agent_id: str,
    artifact_path: str,
    sub_agent_config_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    fallback_agent_ids = [
        agent_id for agent_id in BUILTIN_SUB_AGENT_IDS if agent_id != target_agent_id
    ]
    return await _patch_builtin_agent_config(
        "orchestrator",
        {
            "react_enabled": False,
            "llm_planning": False,
            "available_agents_authoritative": False,
            "orchestrator_parallel_enabled": False,
            "orchestrator_runtime_cooldown_enabled": False,
            "max_task_attempts": 3,
            "managed_agent_ids": list(BUILTIN_SUB_AGENT_IDS),
            "task_fallback_agent_ids": fallback_agent_ids,
            "sub_agent_config_overrides": {
                agent_id: dict(agent_config)
                for agent_id, agent_config in (sub_agent_config_overrides or {}).items()
            },
            "tasks": [
                {
                    "task_id": "fallback-task",
                    "agent_id": target_agent_id,
                    "title": "Create fallback evidence",
                    "instruction": (
                        f"Create `{artifact_path}` as a markdown file in the current "
                        "workspace. Use the native `write_file` tool with path exactly "
                        f"`{artifact_path}`; do not use bash, shell commands, absolute "
                        "paths, `/workspace`, or `file_path`. Include the line "
                        f"`AGENT_FALLBACK_SENTINEL={target_agent_id}`. If a previous "
                        "Agent failed, continue from the failure context and finish "
                        "the same artifact."
                    ),
                    "expected_output": artifact_path,
                }
            ],
        },
    )


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


def fallback_group_agent_ids(target_agent_id: str) -> list[str]:
    return [
        "orchestrator",
        target_agent_id,
        *(agent_id for agent_id in BUILTIN_SUB_AGENT_IDS if agent_id != target_agent_id),
    ]


def _ensure_agent_fallback_matrix_runtime_helpers() -> None:
    fail_runtime = Path(AGENT_FALLBACK_E2E_FAIL_RUNTIME)
    fail_runtime.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "sys.stderr.write('E2E forced runtime failure\\n')",
                "raise SystemExit(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fail_runtime.chmod(fail_runtime.stat().st_mode | stat.S_IXUSR)

    write_runtime = Path(AGENT_FALLBACK_E2E_WRITE_RUNTIME)
    write_runtime.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from pathlib import Path",
                "import re",
                "import sys",
                "args = sys.argv[1:]",
                "workspace = Path.cwd()",
                "if '--dir' in args:",
                "    try:",
                "        workspace = Path(args[args.index('--dir') + 1])",
                "    except (IndexError, ValueError):",
                "        pass",
                "prompt = args[-1] if args else ''",
                "path_match = re.search(r'Create `([^`]+)`', prompt)",
                "sentinel_match = re.search(r'`(AGENT_FALLBACK_SENTINEL=[^`]+)`', prompt)",
                "artifact = path_match.group(1) if path_match else 'fallback-evidence.md'",
                "sentinel = (sentinel_match.group(1) if sentinel_match "
                "else 'AGENT_FALLBACK_SENTINEL=e2e')",
                "target = workspace / artifact",
                "target.parent.mkdir(parents=True, exist_ok=True)",
                "target.write_text(",
                "    '# Fallback evidence\\n\\n' + sentinel + '\\n',",
                "    encoding='utf-8',",
                ")",
                "sys.stdout.write(f'Created {artifact}\\n')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_runtime.chmod(write_runtime.stat().st_mode | stat.S_IXUSR)


def _task_cards_from_message(message: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [
        block
        for block in content
        if isinstance(block, dict) and block.get("type") == "task_card"
    ]


def _fallback_task_card_task(
    message: dict[str, Any] | None,
    *,
    task_id: str = "fallback-task",
) -> dict[str, Any]:
    for card in _task_cards_from_message(message):
        tasks = card.get("tasks")
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if isinstance(task, dict) and task.get("id") == task_id:
                return task
    return {}


def _attempts_from_run_detail(run_detail: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(run_detail, dict):
        return []
    attempts: list[dict[str, Any]] = []
    raw_attempts = run_detail.get("attempts")
    if isinstance(raw_attempts, list):
        attempts.extend(item for item in raw_attempts if isinstance(item, dict))
    events = run_detail.get("events")
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict) or event.get("event_type") != "task_result":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            payload_attempts = payload.get("attempts")
            if isinstance(payload_attempts, list):
                attempts.extend(
                    item for item in payload_attempts if isinstance(item, dict)
                )
    return attempts


def _fallback_attempt_agents(
    run_detail: dict[str, Any] | None,
    *,
    target_agent_id: str,
    task_id: str = "fallback-task",
) -> dict[str, Any]:
    attempts = [
        attempt
        for attempt in _attempts_from_run_detail(run_detail)
        if attempt.get("task_id") == task_id
        and attempt.get("state") not in {"pending", "skipped"}
    ]
    attempt_agents = [
        str(attempt.get("agent_id"))
        for attempt in attempts
        if isinstance(attempt.get("agent_id"), str)
    ]
    fallback_agents = [agent_id for agent_id in attempt_agents if agent_id != target_agent_id]
    terminal_attempts = [
        attempt
        for attempt in attempts
        if attempt.get("state") in {"succeeded", "manual_review_required", "done"}
        and isinstance(attempt.get("agent_id"), str)
    ]
    final_agent = None
    if terminal_attempts:
        final_agent = str(terminal_attempts[-1].get("agent_id"))
    elif fallback_agents:
        final_agent = fallback_agents[-1]
    elif attempt_agents:
        final_agent = attempt_agents[-1]
    return {
        "attempt_agents": attempt_agents,
        "fallback_agents": fallback_agents,
        "final_agent": final_agent,
    }


def evaluate_fallback_task_card_case(case_report: dict[str, Any]) -> dict[str, Any]:
    target_agent_id = str(case_report.get("target_agent_id") or "")
    task_card_task = _fallback_task_card_task(case_report.get("target_agent_message"))
    attempt_evidence = _fallback_attempt_agents(
        case_report.get("orchestrator_run_detail"),
        target_agent_id=target_agent_id,
    )
    final_attempt_agent = attempt_evidence.get("final_agent")
    task_agent_id = task_card_task.get("agent_id")
    planned_agent_id = task_card_task.get("planned_agent_id")
    final_agent_id = task_card_task.get("final_agent_id")
    result = {
        "task_card_task": task_card_task,
        "attempt_agents": attempt_evidence["attempt_agents"],
        "fallback_attempt_agents": attempt_evidence["fallback_agents"],
        "final_attempt_agent": final_attempt_agent,
        "planned_agent_matches_target": planned_agent_id == target_agent_id,
        "task_agent_matches_final_attempt": (
            isinstance(final_attempt_agent, str)
            and task_agent_id == final_attempt_agent
        ),
        "final_agent_matches_final_attempt": (
            isinstance(final_attempt_agent, str)
            and final_agent_id == final_attempt_agent
        ),
        "task_agent_reassigned_from_planned": (
            isinstance(task_agent_id, str)
            and isinstance(planned_agent_id, str)
            and task_agent_id != planned_agent_id
        ),
    }
    result["passed"] = all(
        bool(result[key])
        for key in (
            "planned_agent_matches_target",
            "task_agent_matches_final_attempt",
            "final_agent_matches_final_attempt",
            "task_agent_reassigned_from_planned",
        )
    )
    return result


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
    if not isinstance(run_detail, dict):
        return {}
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
    if not isinstance(profile, dict):
        return {}
    report["agent_capability_profile"] = profile
    return profile


def fetch_agent_capability_profile_v2(
    client: httpx.Client,
    headers: dict[str, str],
    conv_id: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/conversations/{conv_id}/agent-capability-profile-v2",
        headers=headers,
    )
    report["agent_capability_profile_v2_status_code"] = response.status_code
    if response.status_code != 200:
        report["agent_capability_profile_v2_error"] = response.text
        return {}
    profile = response.json()
    if not isinstance(profile, dict):
        return {}
    report["agent_capability_profile_v2"] = profile
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


def fetch_conversation_messages(
    client: httpx.Client,
    headers: dict[str, str],
    conv_id: str,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    report["conversation_messages_status_code"] = response.status_code
    if response.status_code != 200:
        report["conversation_messages_error"] = response.text
        return []
    items = response.json().get("items", [])
    return items if isinstance(items, list) else []


def message_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = message.get("content")
    return blocks if isinstance(blocks, list) else []


def all_visible_message_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(visible_agent_text(message_blocks(message)) for message in messages)


def process_block_count(messages: list[dict[str, Any]]) -> int:
    return sum(
        1
        for message in messages
        for block in message_blocks(message)
        if isinstance(block, dict) and block.get("type") == "process"
    )


def workflow_blocks_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        block
        for message in messages
        for block in message_blocks(message)
        if isinstance(block, dict) and block.get("type") == "workflow"
    ]


def forbidden_visible_terms(text: str) -> list[str]:
    text = re.sub(r"/api/v1/workspaces/[A-Za-z0-9_.-]+/files/", "/api/v1/workspace-files/", text)
    return [term for term in FORBIDDEN_VISIBLE_TRACE_TERMS if term in text]


def message_error_text(events: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for event in events:
        if event.get("event") != "message_error":
            continue
        error = event_data(event).get("error")
        if isinstance(error, str) and error:
            parts.append(error)
    return "\n".join(parts)


def child_messages_for_user(
    messages: list[dict[str, Any]],
    *,
    parent_message_id: str,
    user_message_id: str,
) -> list[dict[str, Any]]:
    return [
        item
        for item in messages
        if item.get("role") == "agent"
        and item.get("id") != parent_message_id
        and item.get("reply_to_id") == user_message_id
        and item.get("agent_id") in BUILTIN_SUB_AGENT_IDS
    ]


def group_process_report(
    events: list[dict[str, Any]],
    parent_message: dict[str, Any],
    child_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    child_ids = {
        str(item.get("id")) for item in child_messages if isinstance(item.get("id"), str)
    }
    child_agents = {
        str(item.get("agent_id"))
        for item in child_messages
        if isinstance(item.get("agent_id"), str)
    }
    message_start_agents = [
        str(event_data(event).get("agent_id"))
        for event in events
        if event.get("event") == "message_start"
        and isinstance(event_data(event).get("agent_id"), str)
    ]
    terminal_agents = [
        str(event_data(event).get("agent_id"))
        for event in events
        if event.get("event") in {"message_done", "message_error"}
        and isinstance(event_data(event).get("agent_id"), str)
    ]
    child_process_delta_count = sum(
        1
        for event in events
        if event.get("event") == "delta"
        and event_data(event).get("message_id") in child_ids
        and isinstance((event_data(event).get("metadata") or {}).get("process_delta"), dict)
    )
    child_process_agents = {
        str(item.get("agent_id"))
        for item in child_messages
        if any(block.get("type") == "process" for block in message_blocks(item))
        and isinstance(item.get("agent_id"), str)
    }
    parent_embedded_child_blocks = [
        block
        for block in message_blocks(parent_message)
        if block.get("agent_id") in BUILTIN_SUB_AGENT_IDS
    ]
    return {
        "message_start_agents": message_start_agents,
        "terminal_agents": terminal_agents,
        "child_agents": sorted(child_agents),
        "child_message_count": len(child_messages),
        "child_process_delta_count": child_process_delta_count,
        "child_process_agents": sorted(child_process_agents),
        "child_process_message_count": len(child_process_agents),
        "parent_embedded_child_block_count": len(parent_embedded_child_blocks),
    }


def block_presentation(block: dict[str, Any]) -> dict[str, Any]:
    presentation = block.get("presentation")
    return presentation if isinstance(presentation, dict) else {}


def event_presentation(event: dict[str, Any]) -> dict[str, Any]:
    data = event_data(event)
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    presentation = metadata.get("presentation")
    return presentation if isinstance(presentation, dict) else {}


def presentation_marker_report(
    events: list[dict[str, Any]],
    parent_message: dict[str, Any],
    child_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    all_messages = [parent_message, *child_messages]
    blocks = [
        block
        for message in all_messages
        for block in message_blocks(message)
        if isinstance(block, dict)
    ]
    block_presentations = [
        block_presentation(block) for block in blocks if block_presentation(block)
    ]
    event_presentations = [
        event_presentation(event) for event in events if event_presentation(event)
    ]
    all_presentations = [*block_presentations, *event_presentations]
    roles = [
        str(presentation.get("role"))
        for presentation in all_presentations
        if isinstance(presentation.get("role"), str)
    ]
    boundaries = [
        str(presentation.get("boundary"))
        for presentation in all_presentations
        if isinstance(presentation.get("boundary"), str)
    ]
    child_agent_summaries = [
        block
        for message in child_messages
        for block in message_blocks(message)
        if block_presentation(block).get("role") == "agent_summary"
    ]
    parent_final_answers = [
        block
        for block in message_blocks(parent_message)
        if block_presentation(block).get("role") == "final_answer"
    ]
    collapsible_blocks = [
        block
        for block in blocks
        if block_presentation(block).get("collapsible") is True
    ]
    return {
        "presentation_roles": sorted(set(roles)),
        "presentation_boundaries": sorted(set(boundaries)),
        "persisted_presentation_count": len(block_presentations),
        "sse_presentation_count": len(event_presentations),
        "child_agent_summary_count": len(child_agent_summaries),
        "parent_final_answer_count": len(parent_final_answers),
        "collapsible_block_count": len(collapsible_blocks),
        "child_message_count": len(child_messages),
    }


def run_presentation_collapse_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"Presentation Collapse Smoke {int(started_at)}",
            "mode": "group",
            "agent_ids": AGENT_IDS,
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
    parent_message_id = sent["agent_message"]["id"]
    user_message_id = sent["user_message"]["id"]
    messages = fetch_conversation_messages(client, headers, conv_id, report)
    parent_message = next(
        (item for item in messages if item.get("id") == parent_message_id),
        target or {},
    )
    child_messages = child_messages_for_user(
        messages,
        parent_message_id=parent_message_id,
        user_message_id=user_message_id,
    )
    visible_text = all_visible_message_text([parent_message, *child_messages])
    event_error_text = message_error_text(events)
    forbidden_terms = forbidden_visible_terms(f"{visible_text}\n{event_error_text}")
    marker_report = presentation_marker_report(events, parent_message, child_messages)

    report["user_message_id"] = user_message_id
    report["agent_message_id"] = parent_message_id
    report["target_agent_message"] = parent_message
    report["child_agent_messages"] = child_messages
    report["stream_event_count"] = len(events)
    report["presentation_markers"] = marker_report
    report["presentation_visible_forbidden_terms"] = forbidden_terms
    fetch_orchestrator_run_detail(client, headers, conv_id, report)

    checks = report["checks"]
    checks["message_done"] = parent_message.get("status") == "done"
    checks["presentation_sse_roles_seen"] = marker_report["sse_presentation_count"] > 0
    checks["presentation_persisted_roles_seen"] = (
        marker_report["persisted_presentation_count"] > 0
    )
    checks["presentation_execution_start_seen"] = (
        "execution_start" in marker_report["presentation_boundaries"]
    )
    checks["presentation_answer_start_seen"] = (
        "answer_start" in marker_report["presentation_boundaries"]
    )
    checks["presentation_agent_summary_seen"] = (
        marker_report["child_agent_summary_count"] >= 1
    )
    checks["presentation_final_answer_seen"] = (
        marker_report["parent_final_answer_count"] >= 1
    )
    checks["presentation_collapsible_execution_seen"] = (
        marker_report["collapsible_block_count"] >= 1
    )
    checks["presentation_visible_text_no_forbidden_terms"] = not forbidden_terms

    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "presentation_sse_roles_seen",
        "presentation_persisted_roles_seen",
        "presentation_execution_start_seen",
        "presentation_answer_start_seen",
        "presentation_agent_summary_seen",
        "presentation_final_answer_seen",
        "presentation_collapsible_execution_seen",
        "presentation_visible_text_no_forbidden_terms",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def run_group_dialogue_debate_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"Group Dialogue Debate {int(started_at)}",
            "mode": "group",
            "agent_ids": AGENT_IDS,
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
    parent_message_id = sent["agent_message"]["id"]
    user_message_id = sent["user_message"]["id"]
    messages = fetch_conversation_messages(client, headers, conv_id, report)
    parent_message = next(
        (item for item in messages if item.get("id") == parent_message_id),
        target or {},
    )
    child_messages = child_messages_for_user(
        messages,
        parent_message_id=parent_message_id,
        user_message_id=user_message_id,
    )
    run_detail = fetch_orchestrator_run_detail(client, headers, conv_id, report)
    run_items = report.get("orchestrator_runs")
    run_item = run_items[0] if isinstance(run_items, list) and run_items else {}
    plan_source = run_item.get("plan_source") if isinstance(run_item, dict) else None
    parent_text = visible_agent_text(message_blocks(parent_message))
    visible_text = all_visible_message_text([parent_message, *child_messages])
    forbidden_terms = forbidden_visible_terms(
        f"{visible_text}\n{message_error_text(events)}"
    )
    missing_paths = _unresolved_missing_artifact_paths(run_detail)
    final_summary = str((run_detail.get("run") or {}).get("final_summary") or "")
    child_statuses = [item.get("status") for item in child_messages]
    child_agent_ids = {
        item.get("agent_id")
        for item in child_messages
        if item.get("agent_id") and item.get("agent_id") != "orchestrator"
    }
    child_text = all_visible_message_text(child_messages)
    child_output_contracts = substantive_child_output_report(child_messages, run_detail)

    report["user_message_id"] = user_message_id
    report["agent_message_id"] = parent_message_id
    report["target_agent_message"] = parent_message
    report["child_agent_messages"] = child_messages
    report["child_output_contracts"] = child_output_contracts
    report["stream_event_count"] = len(events)
    report["plan_source"] = plan_source
    report["dialogue_missing_artifact_paths"] = missing_paths
    report["dialogue_visible_forbidden_terms"] = forbidden_terms

    checks = report["checks"]
    checks["message_done"] = parent_message.get("status") == "done"
    checks["plan_not_artifact_legacy_template"] = plan_source != "legacy template"
    checks["at_least_two_child_messages"] = len(child_messages) >= 2
    checks["at_least_two_child_agents"] = len(child_agent_ids) >= 2
    checks["child_messages_terminal"] = bool(child_messages) and all(
        status in {"done", "error"} for status in child_statuses
    )
    checks["no_artifact_missing"] = "artifact_missing" not in final_summary and not missing_paths
    checks["no_server_package_missing"] = not {
        "server.js",
        "package.json",
    }.intersection(missing_paths)
    checks["parent_final_not_failed"] = not any(
        marker in parent_text for marker in ("没能", "未能", "失败", "未完成")
    )
    checks["dialogue_content_present"] = all(
        marker in child_text for marker in ("AI", "利大于弊", "弊大于利")
    )
    checks["done_children_have_substantive_agent_summary"] = (
        _done_children_have_substantive_agent_summary(child_output_contracts)
    )
    checks["error_children_have_readable_failure_or_fallback"] = (
        _error_children_have_readable_failure_or_fallback(child_output_contracts)
    )
    checks["visible_text_no_forbidden_terms"] = not forbidden_terms

    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "plan_not_artifact_legacy_template",
        "at_least_two_child_messages",
        "at_least_two_child_agents",
        "child_messages_terminal",
        "no_artifact_missing",
        "no_server_package_missing",
        "parent_final_not_failed",
        "dialogue_content_present",
        "done_children_have_substantive_agent_summary",
        "error_children_have_readable_failure_or_fallback",
        "visible_text_no_forbidden_terms",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def run_manual_two_agent_turn_taking_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"Manual Two Agent Turn Taking {int(started_at)}",
            "mode": "group",
            "agent_ids": ["claude-code", "opencode-helper"],
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
        content=MANUAL_TWO_AGENT_TURN_TAKING_PROMPT,
        target_agent_id="claude-code",
        started_at=started_at,
    )
    parent_message_id = sent["agent_message"]["id"]
    user_message_id = sent["user_message"]["id"]
    messages = fetch_conversation_messages(client, headers, conv_id, report)
    parent_message = next(
        (item for item in messages if item.get("id") == parent_message_id),
        target or {},
    )
    child_messages = child_messages_for_user(
        messages,
        parent_message_id=parent_message_id,
        user_message_id=user_message_id,
    )
    run_detail = fetch_orchestrator_run_detail(client, headers, conv_id, report)
    contracts = substantive_child_output_report(child_messages, run_detail)
    visible_text = all_visible_message_text([parent_message, *child_messages])
    forbidden_terms = forbidden_visible_terms(
        f"{visible_text}\n{message_error_text(events)}"
    )
    message_start_order = [
        {
            "agent_id": event_data(event).get("agent_id"),
            "message_id": event_data(event).get("message_id"),
            "status": event_data(event).get("status"),
        }
        for event in events
        if event.get("event") == "message_start"
    ]
    terminal_order = [
        {
            "event": event.get("event"),
            "agent_id": event_data(event).get("agent_id"),
            "message_id": event_data(event).get("message_id"),
            "status": event_data(event).get("status"),
        }
        for event in events
        if event.get("event") in {"message_start", "message_done", "message_error"}
    ]
    by_agent: dict[str, list[dict[str, Any]]] = {}
    for message in child_messages:
        agent_id = str(message.get("agent_id") or "")
        if agent_id:
            by_agent.setdefault(agent_id, []).append(message)

    claude_done = any(
        message.get("status") == "done"
        for message in by_agent.get("claude-code", [])
    )
    claude_done_count = sum(
        1
        for message in by_agent.get("claude-code", [])
        if message.get("status") == "done"
    )
    opencode_done = any(
        message.get("status") == "done"
        for message in by_agent.get("opencode-helper", [])
    )
    opencode_contract_passed = any(
        item.get("agent_id") == "opencode-helper"
        and item.get("status") == "done"
        and item.get("substantive_output_passed") is True
        for item in contracts
    )
    saw_required_order = _message_lifecycle_order_seen(
        terminal_order,
        ("claude-code", "message_start"),
        ("claude-code", "message_done"),
        ("opencode-helper", "message_start"),
        ("opencode-helper", "message_done"),
        ("claude-code", "message_start"),
        ("claude-code", "message_done"),
    )
    final_has_debate_judgement = any(
        marker in visible_text for marker in ("辩论评判", "更有说服力", "势均力敌")
    )
    missing_paths = _unresolved_missing_artifact_paths(run_detail)

    report.update(
        {
            "prompt": MANUAL_TWO_AGENT_TURN_TAKING_PROMPT,
            "user_message_id": user_message_id,
            "agent_message_id": parent_message_id,
            "target_agent_message": parent_message,
            "child_agent_messages": child_messages,
            "child_output_contracts": contracts,
            "stream_event_count": len(events),
            "message_start_order": message_start_order,
            "message_lifecycle_order": terminal_order,
            "dialogue_missing_artifact_paths": missing_paths,
            "dialogue_visible_forbidden_terms": forbidden_terms,
        }
    )

    checks = report["checks"]
    checks["message_done"] = parent_message.get("status") == "done"
    checks["two_agent_group_created"] = set(conv.get("agent_ids") or []) >= {
        "claude-code",
        "opencode-helper",
    }
    checks["claude_child_done"] = claude_done
    checks["claude_continued_after_opencode"] = claude_done_count >= 2
    checks["opencode_child_done"] = opencode_done
    checks["opencode_agent_summary_substantive"] = opencode_contract_passed
    checks["required_message_lifecycle_order"] = saw_required_order
    checks["final_answer_has_debate_judgement"] = final_has_debate_judgement
    checks["no_fallback_substitute_for_opencode"] = opencode_done
    checks["no_artifact_missing"] = not missing_paths
    checks["visible_text_no_forbidden_terms"] = not forbidden_terms

    acceptance_keys = (
        "target_agents_present",
        "message_done",
        "two_agent_group_created",
        "claude_child_done",
        "claude_continued_after_opencode",
        "opencode_child_done",
        "opencode_agent_summary_substantive",
        "required_message_lifecycle_order",
        "final_answer_has_debate_judgement",
        "no_fallback_substitute_for_opencode",
        "no_artifact_missing",
        "visible_text_no_forbidden_terms",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def _message_lifecycle_order_seen(
    events: list[dict[str, Any]],
    *expected: tuple[str, str],
) -> bool:
    cursor = 0
    for event in events:
        if cursor >= len(expected):
            break
        expected_agent, expected_event = expected[cursor]
        if event.get("event") == expected_event and event.get("agent_id") == expected_agent:
            cursor += 1
    return cursor == len(expected)


def _unresolved_missing_artifact_paths(run_detail: dict[str, Any]) -> list[str]:
    """Return missing artifacts that were not recovered by a later same-task attempt."""

    raw_attempts = run_detail.get("attempts") if isinstance(run_detail, dict) else []
    attempts = [item for item in raw_attempts if isinstance(item, dict)]
    unresolved: list[str] = []
    for index, attempt in enumerate(attempts):
        missing = [
            str(path)
            for path in attempt.get("missing_artifact_paths", [])
            if isinstance(path, str) and path
        ]
        if not missing:
            continue
        recovered: set[str] = set()
        for later in attempts[index + 1 :]:
            recovered.update(
                str(path)
                for path in later.get("artifact_paths", [])
                if isinstance(path, str) and path
            )
        unresolved.extend(path for path in missing if path not in recovered)
    return list(dict.fromkeys(unresolved))


def substantive_child_output_report(
    child_messages: list[dict[str, Any]],
    run_detail: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fallback_index = _fallback_index_by_agent(run_detail or {})
    return [_child_output_contract(item, fallback_index) for item in child_messages]


def _child_output_contract(
    message: dict[str, Any],
    fallback_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summaries = [
        str(block.get("text") or "")
        for block in message_blocks(message)
        if block.get("type") == "text"
        and (block.get("presentation") or {}).get("role") == "agent_summary"
    ]
    text = "\n".join(summaries).strip()
    failure_reason = ""
    if not text:
        failure_reason = "missing agent_summary"
    elif _looks_like_host_only(text):
        failure_reason = "summary is host-only prompt"
    elif _looks_like_prompt_echo(text):
        failure_reason = "summary contains prompt echo"
    elif _looks_generic_completion(text):
        failure_reason = "summary is generic completion text"
    elif len(re.sub(r"\s+", "", text)) < 60 and not _looks_like_artifact_summary(text):
        failure_reason = "summary too short"
    fallback_data = (fallback_index or {}).get(str(message.get("agent_id") or ""), {})
    status = str(message.get("status") or "")
    if status != "done":
        error_text = visible_agent_text(message_blocks(message))
        failure_reason = ""
        if not error_text.strip() and not fallback_data.get("fallback_agent_id"):
            failure_reason = "error child missing readable failure or fallback evidence"
        return {
            "message_id": message.get("id"),
            "agent_id": message.get("agent_id"),
            "status": message.get("status"),
            "output_contract_type": "error_attempt",
            "requires_agent_summary": False,
            "substantive_output_passed": False,
            "terminal_output_accepted": not failure_reason,
            "retry_count": _message_output_retry_count(message),
            "fallback_agent_id": fallback_data.get("fallback_agent_id"),
            "failed_source_agent_ids": fallback_data.get("failed_source_agent_ids", []),
            "summary_chars": 0,
            "failure_reason": failure_reason,
            "summary_preview": error_text[:500],
        }
    return {
        "message_id": message.get("id"),
        "agent_id": message.get("agent_id"),
        "status": message.get("status"),
        "output_contract_type": "agent_summary",
        "requires_agent_summary": True,
        "substantive_output_passed": not failure_reason,
        "terminal_output_accepted": not failure_reason,
        "retry_count": _message_output_retry_count(message),
        "fallback_agent_id": fallback_data.get("fallback_agent_id"),
        "failed_source_agent_ids": fallback_data.get("failed_source_agent_ids", []),
        "summary_chars": len(text),
        "failure_reason": failure_reason,
        "summary_preview": text[:500],
    }


def _done_children_have_substantive_agent_summary(
    contracts: list[dict[str, Any]],
) -> bool:
    done_contracts = [item for item in contracts if item.get("status") == "done"]
    return bool(done_contracts) and all(
        item.get("substantive_output_passed") is True for item in done_contracts
    )


def _looks_like_artifact_summary(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    has_completion = any(marker in compact for marker in ("已完成", "完成", "验证"))
    has_artifact_label = any(marker in compact for marker in ("产物", "文件", "审阅产物"))
    has_file = bool(
        re.search(
            r"[\w./-]+\.(?:html|css|js|ts|tsx|jsx|md|json|yaml|yml|py|txt|csv|zip)",
            text,
            re.I,
        )
    )
    return has_completion and has_artifact_label and has_file


def _error_children_have_readable_failure_or_fallback(
    contracts: list[dict[str, Any]],
) -> bool:
    return all(
        item.get("terminal_output_accepted") is True
        for item in contracts
        if item.get("status") != "done"
    )


def _looks_like_host_only(text: str) -> bool:
    if len(text) > 240:
        return False
    return bool(
        re.search(
            r"请.*登场|下面有请|有请.+发言|我来主持|作为主持|正式开始|请.*发表|该你了|轮到你了",
            text,
            re.I,
        )
    )


def _looks_generic_completion(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if any(
        marker in compact
        for marker in (
            "产物：",
            "验证：",
            "文件：",
            "index.html",
            "styles.css",
            "app.js",
            "planning.md",
            "review.md",
        )
    ):
        return False
    return bool(re.fullmatch(r"(已完成|完成|done)[:：]?.{0,80}", compact, re.I))


def _looks_like_prompt_echo(text: str) -> bool:
    prompt_terms = (
        "请直接输出你的具体建议",
        "以下是背景",
        "请保持简洁",
        "你正在参加",
        "不要写完整的报告",
        "原始任务",
    )
    return any(term in text for term in prompt_terms)


def _message_output_retry_count(message: dict[str, Any]) -> int:
    count = 0
    for block in message_blocks(message):
        if not isinstance(block, dict) or block.get("type") != "process":
            continue
        steps = block.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("id") == "output-correction" or "补充实质输出" in str(
                step.get("label") or ""
            ):
                count += 1
    return count


def _fallback_index_by_agent(run_detail: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attempts = run_detail.get("attempts") if isinstance(run_detail, dict) else []
    if not isinstance(attempts, list):
        return {}
    by_task: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        task_id = str(attempt.get("task_id") or "")
        agent_id = str(attempt.get("agent_id") or "")
        if not task_id or not agent_id:
            continue
        by_task.setdefault(task_id, []).append(attempt)

    index: dict[str, dict[str, Any]] = {}
    for task_attempts in by_task.values():
        ordered = sorted(
            task_attempts,
            key=lambda item: int(item.get("attempt_index") or 0),
        )
        failed_agents = [
            str(item.get("agent_id"))
            for item in ordered
            if str(item.get("state") or "") != "succeeded"
        ]
        successful = next(
            (
                item
                for item in ordered
                if str(item.get("state") or "") == "succeeded"
            ),
            None,
        )
        if successful is None or not failed_agents:
            continue
        success_agent = str(successful.get("agent_id") or "")
        if success_agent:
            index.setdefault(success_agent, {})["failed_source_agent_ids"] = failed_agents
        for failed_agent in failed_agents:
            index.setdefault(failed_agent, {})["fallback_agent_id"] = success_agent
    return index


def run_group_substantive_output_matrix_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(GROUP_SUBSTANTIVE_OUTPUT_MATRIX_CASES, 1):
        name = str(case["name"])
        try:
            case_report = _run_substantive_output_case(
                client,
                headers,
                name=name,
                prompt=str(case["prompt"]),
                started_at=started_at + index,
            )
        except Exception as exc:  # noqa: BLE001
            case_report = {
                "name": name,
                "passed": False,
                "error": repr(exc),
                "checks": {"case_exception": False},
            }
        cases.append(case_report)
        report["matrix_cases"] = cases
        report["partial"] = True
        write_json(REPORT_PATH, report)

    report["matrix_cases"] = cases
    report["partial"] = False
    checks = report["checks"]
    checks["matrix_all_cases_passed"] = bool(cases) and all(
        item.get("passed") is True for item in cases
    )
    checks["matrix_each_case_has_child_messages"] = all(
        len(item.get("child_agent_messages") or []) >= 2 for item in cases
    )
    checks["matrix_done_children_have_substantive_agent_summary"] = all(
        _done_children_have_substantive_agent_summary(
            item.get("child_output_contracts") or []
        )
        for item in cases
    )
    checks["matrix_error_children_have_readable_failure_or_fallback"] = all(
        _error_children_have_readable_failure_or_fallback(
            item.get("child_output_contracts") or []
        )
        for item in cases
    )
    checks["matrix_no_artifact_missing"] = all(
        not item.get("dialogue_missing_artifact_paths") for item in cases
    )
    checks["matrix_no_false_document_fulfillment"] = all(
        not item.get("false_document_fulfillment") for item in cases
    )
    checks["matrix_final_text_no_false_document_requirement"] = all(
        not item.get("false_document_final_text") for item in cases
    )
    checks["matrix_visible_text_no_forbidden_terms"] = all(
        not item.get("visible_forbidden_terms") for item in cases
    )
    acceptance_keys = (
        "target_agents_present",
        "matrix_all_cases_passed",
        "matrix_each_case_has_child_messages",
        "matrix_done_children_have_substantive_agent_summary",
        "matrix_error_children_have_readable_failure_or_fallback",
        "matrix_no_artifact_missing",
        "matrix_no_false_document_fulfillment",
        "matrix_final_text_no_false_document_requirement",
        "matrix_visible_text_no_forbidden_terms",
    )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def _run_substantive_output_case(
    client: httpx.Client,
    headers: dict[str, str],
    *,
    name: str,
    prompt: str,
    started_at: float,
) -> dict[str, Any]:
    conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"Substantive Output {name} {int(started_at)}",
            "mode": "group",
            "agent_ids": AGENT_IDS,
        },
    )
    conversation.raise_for_status()
    conv = conversation.json()
    sent, events, target = send_message_and_stream(
        client,
        headers,
        conv["id"],
        content=prompt,
        target_agent_id="orchestrator",
        started_at=started_at,
    )
    parent_message_id = sent["agent_message"]["id"]
    user_message_id = sent["user_message"]["id"]
    case_report: dict[str, Any] = {
        "name": name,
        "conversation_id": conv["id"],
        "user_message_id": user_message_id,
        "agent_message_id": parent_message_id,
        "stream_event_count": len(events),
    }
    messages = fetch_conversation_messages(client, headers, conv["id"], case_report)
    parent_message = next(
        (item for item in messages if item.get("id") == parent_message_id),
        target or {},
    )
    child_messages = child_messages_for_user(
        messages,
        parent_message_id=parent_message_id,
        user_message_id=user_message_id,
    )
    run_detail = fetch_orchestrator_run_detail(client, headers, conv["id"], case_report)
    missing_paths = _unresolved_missing_artifact_paths(run_detail)
    visible_text = all_visible_message_text([parent_message, *child_messages])
    parent_visible_text = visible_agent_text(message_blocks(parent_message))
    forbidden_terms = forbidden_visible_terms(
        f"{visible_text}\n{message_error_text(events)}"
    )
    contracts = substantive_child_output_report(child_messages, run_detail)
    fulfillment_statuses = command_fulfillment_statuses(run_detail)
    no_artifact_requested = "不需要生成文件" in prompt or "no file" in prompt.lower()
    false_document_fulfillment = bool(
        no_artifact_requested
        and fulfillment_statuses.get("document") in {"pending", "failed", "skipped"}
    )
    false_document_final_text = bool(no_artifact_requested and "生成文档" in parent_visible_text)
    case_report.update(
        {
            "target_agent_message": parent_message,
            "child_agent_messages": child_messages,
            "child_output_contracts": contracts,
            "dialogue_missing_artifact_paths": missing_paths,
            "visible_forbidden_terms": forbidden_terms,
            "command_fulfillment_statuses": fulfillment_statuses,
            "false_document_fulfillment": false_document_fulfillment,
            "false_document_final_text": false_document_final_text,
        }
    )
    child_agent_ids = {
        item.get("agent_id")
        for item in child_messages
        if item.get("agent_id") and item.get("agent_id") != "orchestrator"
    }
    case_report["checks"] = {
        "message_done": parent_message.get("status") == "done",
        "at_least_two_child_messages": len(child_messages) >= 2,
        "at_least_two_child_agents": len(child_agent_ids) >= 2,
        "child_messages_terminal": bool(child_messages)
        and all(item.get("status") in {"done", "error"} for item in child_messages),
        "done_children_have_substantive_agent_summary": (
            _done_children_have_substantive_agent_summary(contracts)
        ),
        "error_children_have_readable_failure_or_fallback": (
            _error_children_have_readable_failure_or_fallback(contracts)
        ),
        "no_artifact_missing": not missing_paths,
        "no_false_document_fulfillment": not false_document_fulfillment,
        "final_text_no_false_document_requirement": not false_document_final_text,
        "visible_text_no_forbidden_terms": not forbidden_terms,
    }
    case_report["passed"] = all(case_report["checks"].values())
    return case_report


def command_fulfillment_statuses(run_detail: dict[str, Any]) -> dict[str, str]:
    events = run_detail.get("events") if isinstance(run_detail, dict) else []
    events = events if isinstance(events, list) else []
    payloads = [
        event.get("payload")
        for event in events
        if isinstance(event, dict)
        and event.get("event_type") == "command_fulfillment_status"
        and isinstance(event.get("payload"), dict)
    ]
    status_rank = {"pending": 0, "skipped": 1, "failed": 2, "satisfied": 3}
    statuses: dict[str, str] = {}
    ranks: dict[str, int] = {}
    for payload in payloads:
        items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            item_id = str(item.get("id"))
            status = str(item.get("status") or "pending")
            rank = status_rank.get(status, 0)
            if rank >= ranks.get(item_id, -1):
                statuses[item_id] = status
                ranks[item_id] = rank
    return statuses


CONTEXT_FOLLOWUP_PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "name": "generated_status",
        "content": "主题是赛博朋克风的网站生成了吗",
        "required_terms": ("index.html", "styles.css", "app.js"),
    },
    {
        "name": "preview_url",
        "content": "预览地址是什么",
        "required_terms": ("http", "8082"),
    },
    {
        "name": "browser_verify",
        "content": "浏览器验收通过了吗",
        "required_terms": ("验收",),
    },
    {
        "name": "changed_files",
        "content": "改了哪些文件",
        "required_terms": ("index.html", "styles.css", "app.js"),
    },
    {
        "name": "continue_missing_deployment",
        "content": "继续完成缺失的部署",
        "required_terms": ("部署",),
    },
)


def run_context_followup_checks(
    client: httpx.Client,
    headers: dict[str, str],
    conv_id: str,
    report: dict[str, Any],
    started_at: float,
) -> None:
    followups: list[dict[str, Any]] = []
    checks: dict[str, bool] = {}
    for spec in CONTEXT_FOLLOWUP_PROMPTS:
        name = str(spec["name"])
        sent, events, target = send_message_and_stream(
            client,
            headers,
            conv_id,
            content=str(spec["content"]),
            target_agent_id="orchestrator",
            started_at=started_at,
        )
        messages = fetch_conversation_messages(client, headers, conv_id, report)
        visible_text = visible_agent_text(message_blocks(target or {}))
        event_error_text = message_error_text(events)
        child_messages = child_messages_for_user(
            messages,
            parent_message_id=str((target or {}).get("id") or ""),
            user_message_id=str((sent.get("user_message") or {}).get("id") or ""),
        )
        message_start_agents = [
            str(event_data(event).get("agent_id"))
            for event in events
            if event.get("event") == "message_start"
            and event_data(event).get("agent_id") in BUILTIN_SUB_AGENT_IDS
        ]
        forbidden_terms = forbidden_visible_terms(
            "\n".join((visible_text, event_error_text))
        )
        required_terms = tuple(str(item) for item in spec.get("required_terms", ()))
        required_terms_present = all(term in visible_text for term in required_terms)
        no_internal_error = not any(
            marker in visible_text
            for marker in (
                "invalid_task_plan",
                "planner did not return valid JSON",
                "external_runtime_error",
            )
        )
        item_report = {
            "name": name,
            "content": spec["content"],
            "user_message_id": (sent.get("user_message") or {}).get("id"),
            "agent_message_id": (sent.get("agent_message") or {}).get("id"),
            "status": (target or {}).get("status"),
            "visible_text": visible_text,
            "event_count": len(events),
            "child_message_count": len(child_messages),
            "message_start_agents": message_start_agents,
            "forbidden_terms": forbidden_terms,
            "required_terms_present": required_terms_present,
            "no_internal_error": no_internal_error,
        }
        item_report["passed"] = bool(
            (target or {}).get("status") == "done"
            and not child_messages
            and not message_start_agents
            and not forbidden_terms
            and required_terms_present
            and no_internal_error
        )
        followups.append(item_report)
        checks[f"context_followup_{name}_passed"] = bool(item_report["passed"])
    report["context_followups"] = followups
    checks["context_followups_all_passed"] = all(checks.values())
    report["checks"].update(checks)


def command_fulfillment_review_independent(run_detail: dict[str, Any]) -> bool:
    tasks = run_detail.get("tasks") if isinstance(run_detail, dict) else []
    attempts = run_detail.get("attempts") if isinstance(run_detail, dict) else []
    tasks = tasks if isinstance(tasks, list) else []
    attempts = attempts if isinstance(attempts, list) else []
    task_by_id = {
        str(task.get("task_id") or task.get("id")): task
        for task in tasks
        if isinstance(task, dict) and (task.get("task_id") or task.get("id"))
    }
    final_agents: dict[str, str] = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        task_id = attempt.get("task_id")
        agent_id = attempt.get("agent_id")
        state = attempt.get("state") or attempt.get("final_state")
        if isinstance(task_id, str) and isinstance(agent_id, str) and state == "succeeded":
            final_agents[task_id] = agent_id
    for task_id, task in task_by_id.items():
        if task.get("task_type") != "review":
            continue
        review_agent = final_agents.get(task_id) or task.get("agent_id")
        if not isinstance(review_agent, str):
            continue
        reviewed_ids = task.get("review_of") or task.get("depends_on") or []
        if not isinstance(reviewed_ids, list):
            continue
        reviewed_agents = {
            final_agents.get(str(reviewed_id))
            or task_by_id.get(str(reviewed_id), {}).get("agent_id")
            for reviewed_id in reviewed_ids
        }
        reviewed_agents = {agent for agent in reviewed_agents if isinstance(agent, str)}
        if reviewed_agents and review_agent not in reviewed_agents:
            return True
    return False


def evaluate_generic_group_process(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    events: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> None:
    case = GENERIC_GROUP_PROCESS_CASES[SCENARIO]
    conv_id = str(report["conversation_id"])
    parent_message_id = str(report["agent_message_id"])
    user_message_id = str(report["user_message_id"])
    messages = fetch_conversation_messages(client, headers, conv_id, report)
    target = next((item for item in messages if item.get("id") == parent_message_id), {})
    child_messages = child_messages_for_user(
        messages,
        parent_message_id=parent_message_id,
        user_message_id=user_message_id,
    )
    report["child_agent_messages"] = child_messages
    report["group_chat"] = group_process_report(events, target, child_messages)

    file_names = {str(item.get("path", "")).rsplit("/", 1)[-1] for item in files}
    required_files = set(case.get("required_files") or set())
    missing_files = sorted(required_files - file_names)
    child_statuses = {
        str(item.get("id")): item.get("status") for item in child_messages
    }
    visible_text = all_visible_message_text([target, *child_messages])
    forbidden_terms = forbidden_visible_terms(visible_text)
    group_chat = report["group_chat"]
    required_child_agents = set(case.get("required_child_agents") or set())
    min_child_messages = int(case.get("min_child_messages") or 1)
    allow_child_error = bool(case.get("allow_child_error"))
    terminal_statuses = {"done", "error"} if allow_child_error else {"done"}
    child_agent_set = set(group_chat["child_agents"])
    message_start_agent_set = set(group_chat["message_start_agents"])
    child_process_agent_set = set(group_chat["child_process_agents"])
    required_child_agents_seen = (
        required_child_agents <= child_agent_set
        if required_child_agents
        else len(child_agent_set) >= min_child_messages
    )
    required_message_start_seen = (
        required_child_agents <= message_start_agent_set
        if required_child_agents
        else len(message_start_agent_set) >= min_child_messages
    )
    child_process_blocks_seen = (
        required_child_agents <= child_process_agent_set
        if required_child_agents
        else len(child_process_agent_set) >= min_child_messages
    )

    checks = report["checks"]
    checks["generic_group_message_done"] = target.get("status") == "done"
    checks["generic_group_child_messages_present"] = (
        len(child_messages) >= min_child_messages
    )
    checks["generic_group_required_child_agents_seen"] = required_child_agents_seen
    checks["generic_group_message_start_seen"] = required_message_start_seen
    checks["generic_group_child_terminal"] = all(
        status in terminal_statuses for status in child_statuses.values()
    ) and len(child_statuses) >= min_child_messages
    checks["generic_group_child_process_blocks"] = child_process_blocks_seen
    checks["generic_group_child_process_delta_seen"] = (
        int(group_chat["child_process_delta_count"]) >= min_child_messages
    )
    checks["generic_group_parent_not_embedding_child_blocks"] = (
        int(group_chat["parent_embedded_child_block_count"]) == 0
    )
    checks["generic_group_required_workspace_files"] = not missing_files
    checks["generic_group_visible_text_no_forbidden_terms"] = not forbidden_terms
    checks["generic_group_final_text_no_missing_or_pending"] = (
        "artifact_missing" not in final_summary_from_report(report)
        and "\n- pending:" not in final_summary_from_report(report)
    )
    if case.get("require_failure_text"):
        checks["generic_group_failure_text_readable"] = bool(
            re.search(r"失败|无法|不能|安全|限制|workspace|路径|重试", visible_text, re.I)
        )
    if case.get("require_workflow"):
        workflow_blocks = workflow_blocks_from_messages([target, *child_messages])
        report["generic_workflow_blocks"] = workflow_blocks
        checks["generic_group_workflow_block_present"] = bool(workflow_blocks)
        checks["generic_group_workflow_validation_passed"] = any(
            block.get("validation_status") == "passed" for block in workflow_blocks
        )
        checks["generic_group_workflow_dry_run_passed"] = any(
            block.get("dry_run_status") == "passed" for block in workflow_blocks
        )

    report["generic_group_process"] = {
        "required_files": sorted(required_files),
        "missing_files": missing_files,
        "child_statuses": child_statuses,
        "forbidden_visible_terms": forbidden_terms,
    }
    acceptance_keys = [
        "target_agents_present",
        "orchestrator_llm_planning_enabled",
        "orchestrator_parallel_enabled",
        "message_done",
        "generic_group_message_done",
        "generic_group_child_messages_present",
        "generic_group_required_child_agents_seen",
        "generic_group_message_start_seen",
        "generic_group_child_terminal",
        "generic_group_child_process_blocks",
        "generic_group_child_process_delta_seen",
        "generic_group_parent_not_embedding_child_blocks",
        "generic_group_required_workspace_files",
        "generic_group_visible_text_no_forbidden_terms",
        "generic_group_final_text_no_missing_or_pending",
    ]
    if case.get("require_failure_text"):
        acceptance_keys.append("generic_group_failure_text_readable")
    if case.get("require_workflow"):
        acceptance_keys.extend(
            [
                "generic_group_workflow_block_present",
                "generic_group_workflow_validation_passed",
                "generic_group_workflow_dry_run_passed",
            ]
        )
    report["acceptance"] = {
        key: bool(checks.get(key, False)) for key in acceptance_keys
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


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


def _collect_and_evaluate_p1_rich_artifacts(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
) -> None:
    from .evaluators import evaluate_p1_rich_artifacts

    conv_id = str(report["conversation_id"])
    report["workspace_artifacts_api"] = get_workspace_artifacts(client, conv_id, headers)
    evaluate_p1_rich_artifacts(report)


def _collect_and_evaluate_p1_evaluation_repair(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
) -> None:
    from .evaluators import evaluate_p1_evaluation_repair

    conv_id = str(report["conversation_id"])
    report["workspace_artifacts_api"] = get_workspace_artifacts(client, conv_id, headers)
    evaluate_p1_evaluation_repair(report)


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


def evaluate_p2_agent_capability_profile_v2(report: dict[str, Any]) -> None:
    profile_before = report.get("agent_capability_profile_v2_before_followup")
    profile_before_items = (
        profile_before.get("items", []) if isinstance(profile_before, dict) else []
    )
    before_by_agent = {
        str(item.get("agent_id")): item
        for item in profile_before_items
        if isinstance(item, dict) and item.get("agent_id")
    }
    preferences = (
        profile_before.get("preferences", {})
        if isinstance(profile_before, dict)
        else {}
    )
    final_summary = final_summary_from_report(report).lower()
    target_text = visible_agent_text(p1_content_blocks(report)).lower()
    combined_text = f"{final_summary}\n{target_text}"
    run_detail = report.get("orchestrator_run_detail")
    tasks = run_detail.get("tasks", []) if isinstance(run_detail, dict) else []
    attempts = run_detail.get("attempts", []) if isinstance(run_detail, dict) else []
    followup_tasks = [
        task
        for task in tasks
        if isinstance(task, dict) and _is_capability_v2_followup_task(task)
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
    artifact_preferences = (
        preferences.get("artifact_preferences", {})
        if isinstance(preferences, dict)
        else {}
    )
    checks: dict[str, bool] = {}
    checks["p2_agent_capability_v2_api_user_scope"] = (
        isinstance(profile_before, dict)
        and profile_before.get("scope") == "user"
        and int(profile_before.get("runs_considered") or 0) >= 1
        and int(profile_before.get("source_conversation_count") or 0) >= 1
    )
    followup_runs_before_count = report.get("followup_runs_before_count")
    checks["p2_agent_capability_v2_new_conversation_empty_before_followup"] = (
        isinstance(followup_runs_before_count, int)
        and followup_runs_before_count == 0
    )
    checks["p2_agent_capability_v2_seed_claude_failed"] = (
        int(claude.get("failure_count") or 0) >= 1
        and int(claude.get("evaluation_failed_count") or 0) >= 1
        and int(claude.get("success_count") or 0) == 0
    )
    checks["p2_agent_capability_v2_seed_opencode_succeeded"] = (
        int(opencode.get("success_count") or 0) >= 1
        and float(opencode.get("score") or 0.0) > float(claude.get("score") or 0.0)
    )
    checks["p2_agent_capability_v2_preferences_present"] = (
        isinstance(artifact_preferences, dict)
        and int(artifact_preferences.get("document") or 0) >= 1
    )
    checks["p2_agent_capability_v2_request_no_explicit_agent"] = not any(
        marker in P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
        for marker in ("claude-code", "opencode-helper", "codex-helper")
    )
    checks["p2_agent_capability_v2_memory_context_mentioned"] = (
        "agent capability profile v2 from recent user orchestrator runs"
        in combined_text
        or "user-scope" in combined_text
        or "capability profile v2" in combined_text
    )
    checks["p2_agent_capability_v2_preference_memory_mentioned"] = (
        "user preference memory from recent orchestrator runs" in combined_text
        or "user preference" in combined_text
        or "用户偏好" in combined_text
    )
    checks["p2_agent_capability_v2_followup_task_agent_opencode"] = (
        bool(followup_tasks) and followup_task_agents == {"opencode-helper"}
    )
    checks["p2_agent_capability_v2_followup_attempt_agent_opencode"] = (
        bool(followup_attempts) and followup_attempt_agents == {"opencode-helper"}
    )
    checks["p2_agent_capability_v2_followup_artifact_created"] = any(
        item.get("path") == "p2-capability-v2-followup.md"
        for item in report.get("workspace_files", [])
        if isinstance(item, dict)
    )
    report["agent_capability_profile_v2_before_agents"] = sorted(before_by_agent)
    report["agent_capability_v2_followup_task_agents"] = sorted(followup_task_agents)
    report["agent_capability_v2_followup_attempt_agents"] = sorted(
        followup_attempt_agents
    )
    report["acceptance"] = {
        key: checks[key]
        for key in (
            "p2_agent_capability_v2_api_user_scope",
            "p2_agent_capability_v2_new_conversation_empty_before_followup",
            "p2_agent_capability_v2_seed_claude_failed",
            "p2_agent_capability_v2_seed_opencode_succeeded",
            "p2_agent_capability_v2_preferences_present",
            "p2_agent_capability_v2_request_no_explicit_agent",
            "p2_agent_capability_v2_memory_context_mentioned",
            "p2_agent_capability_v2_preference_memory_mentioned",
            "p2_agent_capability_v2_followup_task_agent_opencode",
            "p2_agent_capability_v2_followup_attempt_agent_opencode",
            "p2_agent_capability_v2_followup_artifact_created",
        )
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def _is_capability_v2_followup_task(task: dict[str, Any]) -> bool:
    text = "\n".join(
        str(task.get(key) or "") for key in ("title", "instruction", "expected_output")
    )
    return "p2-capability-v2-followup.md" in text


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


def run_p2_agent_capability_profile_v2_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    seed_conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"{SCENARIO} Seed Live E2E {int(started_at)}",
            "mode": "group",
            "agent_ids": P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS,
        },
    )
    seed_conversation.raise_for_status()
    seed_conv = seed_conversation.json()
    seed_conv_id = seed_conv["id"]
    report["seed_conversation"] = seed_conv
    report["seed_conversation_id"] = seed_conv_id

    seed_sent, seed_events, seed_target = send_message_and_stream(
        client,
        headers,
        seed_conv_id,
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
    fetch_agent_capability_profile_v2(client, headers, seed_conv_id, report)
    report["agent_capability_profile_v2_after_seed"] = report.get(
        "agent_capability_profile_v2",
        {},
    )

    followup_conversation = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"{SCENARIO} Followup Live E2E {int(started_at)}",
            "mode": "group",
            "agent_ids": P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS,
        },
    )
    followup_conversation.raise_for_status()
    followup_conv = followup_conversation.json()
    followup_conv_id = followup_conv["id"]
    report["conversation"] = followup_conv
    report["conversation_id"] = followup_conv_id

    runs_before = client.get(
        f"/api/v1/conversations/{followup_conv_id}/orchestrator-runs",
        headers=headers,
    )
    report["followup_runs_before_status_code"] = runs_before.status_code
    if runs_before.status_code == 200:
        runs_before_items = runs_before.json().get("items", [])
        report["followup_runs_before_count"] = len(runs_before_items)

    fetch_agent_capability_profile_v2(client, headers, followup_conv_id, report)
    report["agent_capability_profile_v2_before_followup"] = report.get(
        "agent_capability_profile_v2",
        {},
    )

    sent, events, target = send_message_and_stream(
        client,
        headers,
        followup_conv_id,
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
    fetch_orchestrator_run_detail(client, headers, followup_conv_id, report)
    fetch_agent_capability_profile_v2(client, headers, followup_conv_id, report)
    fetch_workspace_evidence(client, headers, followup_conv_id, report)
    report["content_block_types"] = [
        block.get("type") for block in p1_content_blocks(report)
    ]
    evaluate_p2_agent_capability_profile_v2(report)


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
            _collect_and_evaluate_p1_rich_artifacts(client, headers, report)
        elif P1_EVALUATION_REPAIR_SCENARIO:
            _collect_and_evaluate_p1_evaluation_repair(client, headers, report)
    finally:
        if original_review_config is not None:
            try:
                restore = asyncio.run(_restore_orchestrator_config(original_review_config))
            except Exception as exc:  # noqa: BLE001
                restore = {"restored": False, "error": str(exc)}
            report["review_config_restore"] = restore


def run_generic_group_process_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    events, files = p1_common_evidence(
        client,
        headers,
        report,
        started_at,
        title=f"{SCENARIO} Live E2E {int(started_at)}",
        agent_ids=AGENT_IDS,
    )
    evaluate_generic_group_process(client, headers, report, events, files)


def run_agent_fallback_matrix_case(
    client: httpx.Client,
    headers: dict[str, str],
    report: dict[str, Any],
    started_at: float,
) -> None:
    _ensure_agent_fallback_matrix_runtime_helpers()
    case_reports: list[dict[str, Any]] = []
    for case in AGENT_FALLBACK_MATRIX_CASES:
        target_agent_id = str(case["target_agent_id"])
        artifact_path = str(case["artifact_path"])
        case_report: dict[str, Any] = {
            "name": case["name"],
            "target_agent_id": target_agent_id,
            "artifact_path": artifact_path,
            "checks": {},
        }
        original_orchestrator_config: dict[str, Any] | None = None
        original_agent_provider: str | None = None
        fallback_agent_id = str(case["fallback_agent_id"])
        original_fallback_agent_config: dict[str, Any] | None = None
        try:
            provider_patch = case.get("agent_provider_patch")
            if isinstance(provider_patch, str) and provider_patch.strip():
                original_agent_provider = asyncio.run(
                    _patch_agent_provider(target_agent_id, provider_patch.strip())
                )
            original_fallback_agent_config = asyncio.run(
                _patch_builtin_agent_config(
                    fallback_agent_id,
                    {
                        "allowed_tools": ["write_file"],
                        "max_iterations": 4,
                    },
                )
            )
            original_orchestrator_config = asyncio.run(
                _patch_orchestrator_static_task_config(
                    target_agent_id=target_agent_id,
                    fallback_agent_id=fallback_agent_id,
                    artifact_path=artifact_path,
                    sub_agent_config_overrides=case.get("sub_agent_config_overrides"),
                )
            )
            conversation = client.post(
                "/api/v1/conversations",
                headers=headers,
                json={
                    "title": f"{case['name']} Live E2E {int(started_at)}",
                    "mode": "group",
                    "agent_ids": fallback_group_agent_ids(target_agent_id),
                },
            )
            conversation.raise_for_status()
            conv = conversation.json()
            conv_id = conv["id"]
            case_report["conversation"] = conv
            case_report["conversation_id"] = conv_id

            sent, events, target = send_message_and_stream(
                client,
                headers,
                conv_id,
                content=AGENT_FALLBACK_MATRIX_PROMPT,
                target_agent_id="orchestrator",
                started_at=started_at,
            )
            user_message_id = sent["user_message"]["id"]
            parent_message_id = sent["agent_message"]["id"]
            case_report["user_message_id"] = user_message_id
            case_report["agent_message_id"] = parent_message_id
            case_report["target_agent_message"] = target
            case_report["stream_event_count"] = len(events)
            case_report["agent_switch_to_agents"] = [
                event_data(event).get("to_agent")
                for event in events
                if event.get("event") == "agent_switch"
            ]
            fetch_orchestrator_run_detail(client, headers, conv_id, case_report)
            files = fetch_workspace_evidence(client, headers, conv_id, case_report)
            messages = fetch_conversation_messages(client, headers, conv_id, case_report)
            child_messages = child_messages_for_user(
                messages,
                parent_message_id=parent_message_id,
                user_message_id=user_message_id,
            )
            case_report["child_agent_messages"] = child_messages
            case_report["group_chat"] = group_process_report(
                events,
                target or {},
                child_messages,
            )
            visible_text = all_visible_message_text([target or {}, *child_messages])
            forbidden_terms = forbidden_visible_terms(visible_text)
            file_names = {str(item.get("path", "")).rsplit("/", 1)[-1] for item in files}
            switches = [
                str(agent_id)
                for agent_id in case_report["agent_switch_to_agents"]
                if isinstance(agent_id, str)
            ]
            fallback_agents = [
                agent_id for agent_id in switches if agent_id != target_agent_id
            ]
            child_statuses = {
                str(item.get("agent_id")): item.get("status") for item in child_messages
            }
            target_attempted = bool(switches and switches[0] == target_agent_id)
            target_skipped_before_attempt = bool(
                switches
                and switches[0] != target_agent_id
                and child_statuses.get(target_agent_id) is None
            )
            checks = case_report["checks"]
            checks["parent_done"] = bool(target and target.get("status") == "done")
            checks["target_attempted_or_skipped"] = (
                target_attempted or target_skipped_before_attempt
            )
            checks["fallback_agent_selected"] = bool(fallback_agents)
            checks["target_child_error_or_preflight_skip_seen"] = (
                child_statuses.get(target_agent_id) == "error"
                or target_skipped_before_attempt
            )
            checks["fallback_child_done_seen"] = any(
                item.get("agent_id") in fallback_agents and item.get("status") == "done"
                for item in child_messages
            )
            checks["artifact_created"] = artifact_path in file_names
            checks["visible_text_no_forbidden_terms"] = not forbidden_terms
            checks["parent_not_embedding_child_blocks"] = (
                int(case_report["group_chat"]["parent_embedded_child_block_count"]) == 0
            )
            task_card_evidence = evaluate_fallback_task_card_case(case_report)
            case_report["task_card_fallback"] = task_card_evidence
            checks["task_card_planned_agent_matches_target"] = bool(
                task_card_evidence["planned_agent_matches_target"]
            )
            checks["task_card_agent_matches_final_attempt"] = bool(
                task_card_evidence["task_agent_matches_final_attempt"]
            )
            checks["task_card_final_agent_matches_final_attempt"] = bool(
                task_card_evidence["final_agent_matches_final_attempt"]
            )
            checks["task_card_agent_reassigned_from_planned"] = bool(
                task_card_evidence["task_agent_reassigned_from_planned"]
            )
            case_report["fallback_agents"] = fallback_agents
            case_report["target_attempted"] = target_attempted
            case_report["target_skipped_before_attempt"] = target_skipped_before_attempt
            case_report["forbidden_visible_terms"] = forbidden_terms
            case_report["passed"] = all(checks.values())
        except Exception as exc:  # noqa: BLE001
            case_report["error"] = str(exc)
            case_report["passed"] = False
        finally:
            restores: dict[str, Any] = {}
            if original_orchestrator_config is not None:
                try:
                    restores["orchestrator"] = asyncio.run(
                        _restore_orchestrator_config(original_orchestrator_config)
                    )
                except Exception as exc:  # noqa: BLE001
                    restores["orchestrator"] = {"restored": False, "error": str(exc)}
            if original_agent_provider is not None:
                try:
                    restores[f"{target_agent_id}.provider"] = asyncio.run(
                        _restore_agent_provider(target_agent_id, original_agent_provider)
                    )
                except Exception as exc:  # noqa: BLE001
                    restores[f"{target_agent_id}.provider"] = {
                        "restored": False,
                        "error": str(exc),
                    }
            if original_fallback_agent_config is not None:
                try:
                    restores[fallback_agent_id] = asyncio.run(
                        _restore_builtin_agent_config(
                            fallback_agent_id,
                            original_fallback_agent_config,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    restores[fallback_agent_id] = {"restored": False, "error": str(exc)}
            case_report["restores"] = restores
        case_reports.append(case_report)

    report["agent_fallback_matrix"] = case_reports
    checks = report["checks"]
    checks["agent_fallback_matrix_all_cases_ran"] = (
        len(case_reports) == len(AGENT_FALLBACK_MATRIX_CASES)
    )
    checks["agent_fallback_matrix_all_passed"] = all(
        bool(item.get("passed")) for item in case_reports
    )
    report["acceptance"] = {
        "target_agents_present": bool(checks.get("target_agents_present")),
        "agent_fallback_matrix_all_cases_ran": bool(
            checks.get("agent_fallback_matrix_all_cases_ran")
        ),
        "agent_fallback_matrix_all_passed": bool(
            checks.get("agent_fallback_matrix_all_passed")
        ),
    }
    report["acceptance"]["passed"] = all(report["acceptance"].values())


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


def auth_headers(
    client: httpx.Client,
    report: dict[str, Any],
    started_at: float,
) -> dict[str, str]:
    if P2_AGENT_CAPABILITY_PROFILE_V2_SCENARIO and "AGENTHUB_E2E_USERNAME" not in os.environ:
        username = f"cap_v2_e2e_{int(started_at)}_{os.getpid()}"
        password = "P@ssw0rd!12345678"
        register = client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": password},
        )
        report["register_status_code"] = register.status_code
        if register.status_code == 201:
            report["account"] = username
            token = register.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
        report["register_error"] = register.text

    login = client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    report["login_status_code"] = login.status_code
    login.raise_for_status()
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def maybe_run_frontend_ui_smoke(report: dict[str, Any]) -> None:
    if not FRONTEND_UI_SMOKE_ENABLED:
        report["frontend_ui_smoke"] = {"enabled": False}
        return
    conversation_id = report.get("conversation_id")
    screenshot_path = Path(f"/tmp/agenthub_{SCENARIO}_frontend_ui.png")  # noqa: S108
    handoff: dict[str, Any] = {
        "enabled": True,
        "frontend_base_url": FRONTEND_BASE_URL,
        "backend_base_url": BASE_URL,
        "scenario": SCENARIO,
        "conversation_id": conversation_id,
        "agent_message_id": report.get("agent_message_id"),
        "run_id": (report.get("orchestrator_runs") or [{}])[0].get("id")
        if isinstance(report.get("orchestrator_runs"), list)
        else None,
        "screenshot": str(screenshot_path),
        "passed": False,
        "issues": [],
    }
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.goto(f"{FRONTEND_BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
            page.get_by_placeholder("用户名").fill(USERNAME, timeout=10000)
            page.get_by_placeholder("密码").fill(PASSWORD, timeout=10000)
            page.get_by_role("button", name=re.compile("登")).click(timeout=10000)
            try:
                page.wait_for_url(re.compile(r"/chat"), timeout=20000)
            except PlaywrightTimeoutError:
                handoff["issues"].append("login_did_not_reach_chat")
            if isinstance(conversation_id, str) and conversation_id:
                page.goto(
                    f"{FRONTEND_BASE_URL}/chat/{conversation_id}",
                    wait_until="networkidle",
                    timeout=45000,
                )
            page.wait_for_timeout(3000)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            body_text = page.locator("body").inner_text(timeout=10000)
            handoff["checks"] = {
                "page_loaded": "AgentHub" in body_text or "Orchestrator" in body_text,
                "codex_visible": "Codex" in body_text or "codex" in body_text,
                "claude_visible": "Claude" in body_text or "claude" in body_text,
                "opencode_visible": "OpenCode" in body_text or "opencode" in body_text,
                "process_visible": (
                    "思考" in body_text
                    or "执行" in body_text
                    or "process" in body_text.lower()
                ),
                "unknown_block_absent": "不支持的消息块" not in body_text
                and "UnknownBlock" not in body_text,
                "rough_failure_absent": "The delegated task did not complete successfully"
                not in body_text,
            }
            handoff["passed"] = all(handoff["checks"].values())
            if not handoff["passed"]:
                handoff["issues"].append("frontend_ui_rendering_needs_followup")
            browser.close()
    except Exception as exc:  # noqa: BLE001
        handoff["issues"].append("frontend_ui_smoke_exception")
        handoff["error"] = str(exc)
    report["frontend_ui_smoke"] = handoff
    if not handoff.get("passed"):
        write_json(FRONTEND_HANDOFF_REPORT_PATH, handoff)


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
    with httpx.Client(
        base_url=BASE_URL,
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
    ) as client:
        headers = auth_headers(client, report, started_at)
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
        if AGENT_FALLBACK_MATRIX_SCENARIO:
            run_agent_fallback_matrix_case(client, headers, report, started_at)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return
        if GENERIC_GROUP_PROCESS_SCENARIO:
            run_generic_group_process_case(client, headers, report, started_at)
            maybe_run_frontend_ui_smoke(report)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return
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
        if P2_SCENARIO:
            run_p2_agent_capability_profile_v2_case(client, headers, report, started_at)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return
        if PRESENTATION_COLLAPSE_SCENARIO:
            run_presentation_collapse_case(client, headers, report, started_at)
            maybe_run_frontend_ui_smoke(report)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"browser_report={BROWSER_REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return
        if MANUAL_TWO_AGENT_TURN_TAKING_SCENARIO:
            run_manual_two_agent_turn_taking_case(client, headers, report, started_at)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return
        if GROUP_DIALOGUE_DEBATE_SCENARIO or AGENT_TURN_TAKING_DIALOGUE_SCENARIO:
            run_group_dialogue_debate_case(client, headers, report, started_at)
            report["finished_at"] = utc_now()
            report["duration_seconds"] = round(time.time() - started_at, 3)
            report["passed"] = bool(report.get("acceptance", {}).get("passed"))
            write_json(REPORT_PATH, report)
            print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
            print(f"report={REPORT_PATH}")
            print(f"sse={SSE_PATH}")
            return
        if GROUP_SUBSTANTIVE_OUTPUT_MATRIX_SCENARIO or AGENT_TURN_TAKING_MATRIX_SCENARIO:
            run_group_substantive_output_matrix_case(client, headers, report, started_at)
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
        child_messages = [
            item
            for item in items
            if item.get("role") == "agent"
            and item.get("id") != agent_message_id
            and item.get("reply_to_id") == report.get("user_message_id")
            and item.get("agent_id") in {"codex-helper", "claude-code", "opencode-helper"}
        ]
        report["child_agent_messages"] = child_messages
        child_agents = {
            str(item.get("agent_id"))
            for item in child_messages
            if isinstance(item.get("agent_id"), str)
        }
        child_message_ids = {
            str(item.get("id")) for item in child_messages if isinstance(item.get("id"), str)
        }
        message_start_agents = [
            str((event.get("data") or {}).get("agent_id"))
            for event in events
            if event.get("event") == "message_start" and isinstance(event.get("data"), dict)
        ]
        child_process_delta_count = sum(
            1
            for event in events
            if event.get("event") == "delta"
            and isinstance(event.get("data"), dict)
            and (event["data"].get("message_id") in child_message_ids)
            and isinstance((event["data"].get("metadata") or {}).get("process_delta"), dict)
        )
        child_messages_with_process = [
            item
            for item in child_messages
            if any(
                isinstance(block, dict) and block.get("type") == "process"
                for block in (item.get("content") or [])
            )
        ]
        report["group_chat"] = {
            "message_start_agents": message_start_agents,
            "child_agents": sorted(child_agents),
            "child_message_count": len(child_messages),
            "child_process_delta_count": child_process_delta_count,
            "child_process_message_count": len(child_messages_with_process),
        }
        if ARCHITECTED_FRONTEND_GROUP_CHAT_SCENARIO:
            required_child_agents = {"codex-helper", "claude-code", "opencode-helper"}
            report["checks"]["group_child_message_start_all_agents"] = (
                required_child_agents <= set(message_start_agents)
            )
            report["checks"]["group_persisted_child_messages_all_agents"] = (
                required_child_agents <= child_agents
            )
            report["checks"]["group_child_messages_have_process"] = (
                required_child_agents
                <= {
                    str(item.get("agent_id"))
                    for item in child_messages_with_process
                    if isinstance(item.get("agent_id"), str)
                }
            )
            report["checks"]["group_child_process_delta_seen"] = (
                child_process_delta_count >= len(required_child_agents)
            )
            first_child_agent = message_start_agents[0] if message_start_agents else None
            report["checks"]["group_codex_architect_first"] = first_child_agent == "codex-helper"
            report["checks"]["group_parent_does_not_embed_child_outputs"] = not any(
                marker in str((target or {}).get("content") or "")
                for marker in (
                    "已生成 planning.md",
                    "child agent built",
                    "Codex Helper",
                    "Claude Code",
                    "OpenCode Helper",
                )
            )
        if GROUP_PROCESS_FRONTEND_PREVIEW_SCENARIO:
            child_process_agents = {
                str(item.get("agent_id"))
                for item in child_messages_with_process
                if isinstance(item.get("agent_id"), str)
            }
            report["checks"]["group_child_message_start_at_least_2"] = (
                len(set(message_start_agents)) >= 2
            )
            report["checks"]["group_persisted_child_messages_at_least_2"] = (
                len(child_agents) >= 2
            )
            report["checks"]["group_child_messages_have_process_at_least_2"] = (
                len(child_process_agents) >= 2
            )
            report["checks"]["group_child_process_delta_seen"] = (
                child_process_delta_count >= 2
            )
            report["checks"]["group_parent_does_not_embed_child_outputs"] = not any(
                block.get("agent_id") in {"codex-helper", "claude-code", "opencode-helper"}
                for block in ((target or {}).get("content") or [])
                if isinstance(block, dict)
            )

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
            container_status_blocks = [
                block
                for block in deployment_status_blocks
                if block.get("kind") == "container"
            ]
            report["deployment_status_blocks"] = deployment_status_blocks
            report["container_deployment_status_blocks"] = container_status_blocks
            report["checks"]["deployment_tool_called"] = bool(deployment_tool_blocks)
            report["checks"]["source_package_tool_called"] = bool(source_tool_blocks)
            report["checks"]["deployment_status_block_present"] = bool(
                deployment_status_blocks
            )
            report["checks"]["deployment_status_block_has_runtime_metadata"] = any(
                "runtime_kind" in block
                and "runtime_status" in block
                and "failure_category" in block
                and "last_error_code" in block
                for block in container_status_blocks
            )
            deployments = client.get(
                f"/api/v1/workspaces/{conv_id}/deployments",
                headers=headers,
            )
            report["deployment_list_status_code"] = deployments.status_code
            deployments.raise_for_status()
            deployment_items = deployments.json().get("items", [])
            deployment_items = deployment_items if isinstance(deployment_items, list) else []
            initial_container_items = [
                item for item in deployment_items if item.get("kind") == "container"
            ]
            report["expected_container_status"] = EXPECT_CONTAINER_STATUS
            report["container_initial_status"] = (
                initial_container_items[0].get("status")
                if initial_container_items
                else None
            )
            deployment_poll_results: list[dict[str, Any]] = []
            refreshed_deployment_items: list[dict[str, Any]] = []
            for item in deployment_items:
                if item.get("kind") != "container" or item.get("status") not in {
                    "queued",
                    "publishing",
                }:
                    refreshed_deployment_items.append(item)
                    continue
                final_item, poll_elapsed = wait_for_deployment_terminal(
                    client,
                    conv_id,
                    headers,
                    item,
                )
                refreshed_deployment_items.append(final_item)
                deployment_poll_results.append(
                    {
                        "deployment_id": item.get("id"),
                        "initial_status": item.get("status"),
                        "final_status": final_item.get("status"),
                        "elapsed_seconds": round(poll_elapsed, 3),
                    }
                )
            deployment_items = refreshed_deployment_items
            report["deployment_poll_results"] = deployment_poll_results
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
            all_container_items = [
                item for item in deployment_items if item.get("kind") == "container"
            ]
            published_container_items = [
                item for item in all_container_items if item.get("status") == "published"
            ]
            not_supported_container_items = [
                item
                for item in all_container_items
                if item.get("status") == "not_supported"
            ]
            failed_container_items = [
                item
                for item in all_container_items
                if item.get("status") == "failed"
            ]
            stopped_container_items = [
                item
                for item in all_container_items
                if item.get("status") == "stopped"
            ]
            container_final_item = (
                published_container_items[0]
                if published_container_items
                else not_supported_container_items[0]
                if not_supported_container_items
                else failed_container_items[0]
                if failed_container_items
                else stopped_container_items[0]
                if stopped_container_items
                else all_container_items[0]
                if all_container_items
                else None
            )
            report["container_status"] = (
                container_final_item.get("status") if container_final_item else None
            )
            report["container_deployment"] = container_final_item
            report["container_state_event_count"] = (
                len(container_final_item.get("state_events") or [])
                if container_final_item
                else 0
            )
            report["checks"]["deployment_status_block_has_runtime_metadata"] = bool(
                report["checks"].get("deployment_status_block_has_runtime_metadata")
                or (
                    container_final_item
                    and "runtime_kind" in container_final_item
                    and "runtime_status" in container_final_item
                    and "failure_category" in container_final_item
                    and "last_error_code" in container_final_item
                    and "state_events" in container_final_item
                )
            )
            report["checks"]["static_site_deployment_published"] = bool(static_items)
            report["checks"]["container_deployment_terminal"] = bool(
                container_final_item
                and container_final_item.get("status") in CONTAINER_TERMINAL_STATUSES
            )
            report["checks"]["container_status_expected"] = bool(
                container_final_item
                and (
                    EXPECT_CONTAINER_STATUS == "any"
                    or container_final_item.get("status") == EXPECT_CONTAINER_STATUS
                )
            )
            report["checks"]["container_deployment_published"] = bool(
                published_container_items
            )
            report["checks"]["container_deployment_not_supported"] = bool(
                not_supported_container_items
            )
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
            report["checks"]["container_worker_metadata_present"] = False
            report["checks"]["container_state_events_present"] = False
            report["checks"]["container_stop_cleanup_ok"] = False
            if published_container_items:
                published_container = published_container_items[0]
                container_url = published_container.get("url")
                healthcheck_url = published_container.get("healthcheck_url")
                report["container_deployment_url"] = container_url
                report["container_healthcheck_url"] = healthcheck_url
                report["checks"]["container_worker_metadata_present"] = bool(
                    published_container.get("worker_id")
                    and (published_container.get("attempt_count") or 0) >= 1
                )
                report["checks"]["container_state_events_present"] = bool(
                    published_container.get("state_events")
                )
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
                deployment_id = published_container.get("id")
                if isinstance(deployment_id, str):
                    stopped_container = client.delete(
                        f"/api/v1/workspaces/{conv_id}/deployments/{deployment_id}",
                        headers=headers,
                    )
                    report["container_stop_status_code"] = stopped_container.status_code
                    report["checks"]["container_stop_cleanup_ok"] = (
                        stopped_container.status_code == 200
                        and is_url_unavailable(container_url)
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
            report["deployment_reflections"] = deployment_reflections
            report["checks"]["deployment_not_supported_no_repair"] = not (
                EXPECT_CONTAINER_STATUS == "not_supported" and deployment_reflections
            )
            if DEPLOYMENT_REPAIR_SCENARIO:
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
            deployment_checks = [
                "deployment_tool_called",
                "source_package_tool_called",
                "deployment_status_block_present",
                "deployment_status_block_has_runtime_metadata",
                "static_site_deployment_published",
                "static_site_url_200",
                "source_zip_deployment_published",
                "source_zip_downloaded",
                "source_zip_excludes_sensitive_paths",
                "container_deployment_terminal",
                "container_status_expected",
            ]
            if EXPECT_CONTAINER_STATUS == "published":
                deployment_checks.extend(
                    [
                    "container_deployment_published",
                    "container_url_200",
                    "container_health_ok",
                    "container_worker_metadata_present",
                    "container_state_events_present",
                    "container_stop_cleanup_ok",
                    ]
                )
            elif EXPECT_CONTAINER_STATUS == "not_supported":
                deployment_checks.extend(
                    [
                        "container_deployment_not_supported",
                        "deployment_not_supported_no_repair",
                    ]
                )
            if DEPLOYMENT_REPAIR_SCENARIO:
                deployment_checks.extend(
                    [
                        "deployment_repair_initial_failure_seen",
                        "deployment_repair_reflection_created",
                        "deployment_repair_redeploy_called",
                    ]
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

        if COMMAND_FULFILLMENT_FLOW_SCENARIO:
            run_detail = (
                report.get("orchestrator_run_detail")
                if isinstance(report.get("orchestrator_run_detail"), dict)
                else {}
            )
            fulfillment_statuses = command_fulfillment_statuses(run_detail)
            report["command_fulfillment_statuses"] = fulfillment_statuses
            content_blocks = (target or {}).get("content") or []
            deployment_tool_blocks = [
                block
                for block in content_blocks
                if block.get("type") == "tool_call"
                and block.get("tool_name") == "create_deployment"
            ]
            deployment_status_blocks = [
                block
                for block in content_blocks
                if block.get("type") == "deployment_status"
            ]
            deployments = client.get(
                f"/api/v1/workspaces/{conv_id}/deployments",
                headers=headers,
            )
            report["command_deployment_list_status_code"] = deployments.status_code
            deployment_items = (
                deployments.json().get("items", [])
                if deployments.status_code == 200
                else []
            )
            deployment_items = deployment_items if isinstance(deployment_items, list) else []
            static_items = [
                item
                for item in deployment_items
                if item.get("kind") == "static_site"
                and item.get("status") == "published"
            ]
            file_names_lower = {name.lower() for name in file_names}
            report["command_deployments"] = deployment_items
            report["checks"]["command_child_agents_at_least_2"] = len(child_agents) >= 2
            report["checks"]["command_child_process_delta_at_least_2"] = (
                child_process_delta_count >= 2
            )
            report["checks"]["command_review_independent"] = (
                command_fulfillment_review_independent(run_detail)
            )
            report["checks"]["command_document_file_present"] = any(
                name.endswith(".md") and ("design" in name or "plan" in name or "文档" in name)
                for name in file_names_lower
            )
            report["checks"]["command_review_file_present"] = any(
                name.endswith(".md") and "review" in name for name in file_names_lower
            )
            report["checks"]["command_diff_evidence_present"] = (
                any("diff" in name for name in file_names_lower)
                or bool(fulfillment_statuses.get("diff") == "satisfied")
            )
            for item_id in (
                "document",
                "code_artifacts",
                "multi_agent",
                "review",
                "preview",
                "browser_verify",
                "deployment",
                "diff",
            ):
                report["checks"][f"command_fulfillment_{item_id}_satisfied"] = (
                    fulfillment_statuses.get(item_id) == "satisfied"
                )
            report["checks"]["command_deployment_tool_called"] = bool(
                deployment_tool_blocks
            )
            report["checks"]["command_deployment_status_block_present"] = bool(
                deployment_status_blocks
            )
            report["checks"]["command_static_deployment_published"] = bool(static_items)
            if static_items:
                static_url = static_items[0].get("url")
                report["command_static_site_deployment_url"] = static_url
                if isinstance(static_url, str) and static_url.startswith("http"):
                    static_response = httpx.get(static_url, timeout=10, trust_env=False)
                    report["checks"]["command_static_site_url_200"] = (
                        static_response.status_code == 200
                    )
                else:
                    report["checks"]["command_static_site_url_200"] = False
            else:
                report["checks"]["command_static_site_url_200"] = False
            command_parent_visible_text = visible_agent_text(content_blocks)
            contradictory_terms = []
            if fulfillment_statuses.get("deployment") == "satisfied":
                contradictory_terms.extend(
                    term
                    for term in ("尚未完成平台部署", "未完成部署", "尚未部署")
                    if term in command_parent_visible_text
                )
            if fulfillment_statuses.get("browser_verify") == "satisfied":
                contradictory_terms.extend(
                    term
                    for term in ("尚未完成浏览器级验收", "未完成验收", "质量验收未完成")
                    if term in command_parent_visible_text
                )
            report["command_contradictory_final_terms"] = contradictory_terms
            report["checks"]["command_final_text_no_contradictory_completion"] = (
                not contradictory_terms
            )
            container_smoke = client.post(
                f"/api/v1/workspaces/{conv_id}/deployments",
                headers=headers,
                json={"kind": "container"},
            )
            report["container_deployment_smoke_status_code"] = (
                container_smoke.status_code
            )
            container_smoke_body = (
                container_smoke.json()
                if container_smoke.status_code in {200, 201}
                else {"error": container_smoke.text}
            )
            report["container_deployment_smoke"] = container_smoke_body
            report["checks"]["container_deployment_smoke_request_created"] = (
                container_smoke.status_code == 201
                and container_smoke_body.get("kind") == "container"
                and container_smoke_body.get("status")
                in {"not_supported", "queued", "publishing", "published", "failed"}
            )
            if CONTEXT_FOLLOWUP_SCENARIO:
                run_context_followup_checks(
                    client,
                    headers,
                    conv_id,
                    report,
                    started_at,
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
        sse_message_error_text = message_error_text(events)
        sse_message_error_forbidden_terms = forbidden_visible_terms(
            sse_message_error_text
        )
        report["sse_message_error_text"] = sse_message_error_text
        report["sse_message_error_forbidden_terms"] = sse_message_error_forbidden_terms
        report["checks"]["message_error_no_forbidden_terms"] = (
            not sse_message_error_forbidden_terms
        )

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
        if COMMAND_FULFILLMENT_FLOW_SCENARIO:
            hard_checks.pop("planner_used_llm", None)
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
        elif ARCHITECTED_FRONTEND_GROUP_CHAT_SCENARIO:
            hard_checks.update(
                {
                    "group_child_message_start_all_agents": report["checks"].get(
                        "group_child_message_start_all_agents",
                        False,
                    ),
                    "group_persisted_child_messages_all_agents": report["checks"].get(
                        "group_persisted_child_messages_all_agents",
                        False,
                    ),
                    "group_child_messages_have_process": report["checks"].get(
                        "group_child_messages_have_process",
                        False,
                    ),
                    "group_child_process_delta_seen": report["checks"].get(
                        "group_child_process_delta_seen",
                        False,
                    ),
                    "group_codex_architect_first": report["checks"].get(
                        "group_codex_architect_first",
                        False,
                    ),
                    "group_parent_does_not_embed_child_outputs": report["checks"].get(
                        "group_parent_does_not_embed_child_outputs",
                        False,
                    ),
                }
            )
        elif GROUP_PROCESS_FRONTEND_PREVIEW_SCENARIO:
            hard_checks.update(
                {
                    "group_child_message_start_at_least_2": report["checks"].get(
                        "group_child_message_start_at_least_2",
                        False,
                    ),
                    "group_persisted_child_messages_at_least_2": report["checks"].get(
                        "group_persisted_child_messages_at_least_2",
                        False,
                    ),
                    "group_child_messages_have_process_at_least_2": report["checks"].get(
                        "group_child_messages_have_process_at_least_2",
                        False,
                    ),
                    "group_child_process_delta_seen": report["checks"].get(
                        "group_child_process_delta_seen",
                        False,
                    ),
                    "group_parent_does_not_embed_child_outputs": report["checks"].get(
                        "group_parent_does_not_embed_child_outputs",
                        False,
                    ),
                }
            )
        elif COMMAND_FULFILLMENT_SCENARIO:
            hard_checks.update(
                {
                    "command_child_agents_at_least_2": report["checks"].get(
                        "command_child_agents_at_least_2",
                        False,
                    ),
                    "command_child_process_delta_at_least_2": report["checks"].get(
                        "command_child_process_delta_at_least_2",
                        False,
                    ),
                    "command_review_independent": report["checks"].get(
                        "command_review_independent",
                        False,
                    ),
                    "command_document_file_present": report["checks"].get(
                        "command_document_file_present",
                        False,
                    ),
                    "command_review_file_present": report["checks"].get(
                        "command_review_file_present",
                        False,
                    ),
                    "command_diff_evidence_present": report["checks"].get(
                        "command_diff_evidence_present",
                        False,
                    ),
                    "command_fulfillment_document_satisfied": report["checks"].get(
                        "command_fulfillment_document_satisfied",
                        False,
                    ),
                    "command_fulfillment_code_artifacts_satisfied": report["checks"].get(
                        "command_fulfillment_code_artifacts_satisfied",
                        False,
                    ),
                    "command_fulfillment_multi_agent_satisfied": report["checks"].get(
                        "command_fulfillment_multi_agent_satisfied",
                        False,
                    ),
                    "command_fulfillment_review_satisfied": report["checks"].get(
                        "command_fulfillment_review_satisfied",
                        False,
                    ),
                    "command_fulfillment_preview_satisfied": report["checks"].get(
                        "command_fulfillment_preview_satisfied",
                        False,
                    ),
                    "command_fulfillment_browser_verify_satisfied": report["checks"].get(
                        "command_fulfillment_browser_verify_satisfied",
                        False,
                    ),
                    "command_fulfillment_deployment_satisfied": report["checks"].get(
                        "command_fulfillment_deployment_satisfied",
                        False,
                    ),
                    "command_fulfillment_diff_satisfied": report["checks"].get(
                        "command_fulfillment_diff_satisfied",
                        False,
                    ),
                    "command_deployment_tool_called": report["checks"].get(
                        "command_deployment_tool_called",
                        False,
                    ),
                    "command_deployment_status_block_present": report["checks"].get(
                        "command_deployment_status_block_present",
                        False,
                    ),
                    "command_static_deployment_published": report["checks"].get(
                        "command_static_deployment_published",
                        False,
                    ),
                    "command_static_site_url_200": report["checks"].get(
                        "command_static_site_url_200",
                        False,
                    ),
                    "command_final_text_no_contradictory_completion": report[
                        "checks"
                    ].get(
                        "command_final_text_no_contradictory_completion",
                        False,
                    ),
                    "message_error_no_forbidden_terms": report["checks"].get(
                        "message_error_no_forbidden_terms",
                        False,
                    ),
                    "container_deployment_smoke_request_created": report["checks"].get(
                        "container_deployment_smoke_request_created",
                        False,
                    ),
                }
            )
        elif CONTEXT_FOLLOWUP_SCENARIO:
            hard_checks.update(
                {
                    "context_followups_all_passed": report["checks"].get(
                        "context_followups_all_passed",
                        False,
                    ),
                    "command_deployment_tool_called": report["checks"].get(
                        "command_deployment_tool_called",
                        False,
                    ),
                    "command_deployment_status_block_present": report["checks"].get(
                        "command_deployment_status_block_present",
                        False,
                    ),
                    "command_static_deployment_published": report["checks"].get(
                        "command_static_deployment_published",
                        False,
                    ),
                    "command_static_site_url_200": report["checks"].get(
                        "command_static_site_url_200",
                        False,
                    ),
                    "command_final_text_no_contradictory_completion": report[
                        "checks"
                    ].get(
                        "command_final_text_no_contradictory_completion",
                        False,
                    ),
                    "message_error_no_forbidden_terms": report["checks"].get(
                        "message_error_no_forbidden_terms",
                        False,
                    ),
                    "container_deployment_smoke_request_created": report["checks"].get(
                        "container_deployment_smoke_request_created",
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
                    "deployment_status_block_has_runtime_metadata": report["checks"].get(
                        "deployment_status_block_has_runtime_metadata",
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
                    "container_deployment_terminal": report["checks"].get(
                        "container_deployment_terminal",
                        False,
                    ),
                    "container_status_expected": report["checks"].get(
                        "container_status_expected",
                        False,
                    ),
                }
            )
            if EXPECT_CONTAINER_STATUS == "published":
                hard_checks.update(
                    {
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
                        "container_worker_metadata_present": report["checks"].get(
                            "container_worker_metadata_present",
                            False,
                        ),
                        "container_state_events_present": report["checks"].get(
                            "container_state_events_present",
                            False,
                        ),
                        "container_stop_cleanup_ok": report["checks"].get(
                            "container_stop_cleanup_ok",
                            False,
                        ),
                    }
                )
            elif EXPECT_CONTAINER_STATUS == "not_supported":
                hard_checks.update(
                    {
                        "container_deployment_not_supported": report["checks"].get(
                            "container_deployment_not_supported",
                            False,
                        ),
                        "deployment_not_supported_no_repair": report["checks"].get(
                            "deployment_not_supported_no_repair",
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

    maybe_run_frontend_ui_smoke(report)
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
