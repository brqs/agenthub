"""Deterministic command-fulfillment tracking for Orchestrator runs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.agents.orchestrator.types import OrchestratorRunContext, SubTask, TaskState

FULFILLMENT_STATUS_ORDER = {"pending", "satisfied", "failed", "skipped"}

DOC_RE = re.compile(
    r"(?i)(文档|报告|设计文档|planning\.md|plan\.md|review\.md|"
    r"document|\bdoc\b|\breport\b)"
)
CODE_RE = re.compile(
    r"(?i)(代码|产物|网站|站点|网页|页面|前端|html|css|javascript|js|app|website|site)"
)
MULTI_AGENT_RE = re.compile(
    r"(?i)(两个智能体|多个智能体|双智能体|两个 agent|多个 agent|多 agent|"
    r"multi[- ]agent|并行开发|并行执行|交由两个智能体|分工协作|真实群聊)"
)
REVIEW_RE = re.compile(r"(?i)(审阅|评审|复核|review)")
PREVIEW_RE = re.compile(r"(?i)(预览|网页预览|端口|preview|port\\s*\\d{2,5}|808\\d)")
BROWSER_RE = re.compile(r"(?i)(浏览器|质量验收|移动端|按钮|交互|browser|quality|mobile)")
DEPLOY_RE = re.compile(r"(?i)(部署|发布|上线|deploy(?:ed|ment)?)")
DIFF_RE = re.compile(r"(?i)(diff|差异|变更摘要)")
SOURCE_RE = re.compile(r"(?i)(源码|源代码|打包|下载|source|zip)")
DOCUMENT_FILE_RE = re.compile(r"(?i)(planning\.md|plan\.md|review\.md|\.docx?\b)")
NEGATED_DOCUMENT_RE = re.compile(
    r"(?i)(不需要|无需|不要|不必|禁止).{0,12}(生成文件|生成文档|写文档|"
    r"书面书写|写报告|生成报告|报告|文档|文件)"
)


def initialize_fulfillment(run_context: OrchestratorRunContext, user_request: str) -> None:
    if run_context.fulfillment_items:
        return
    run_context.fulfillment_items = _items_for_request(user_request)


def fulfillment_payload(run_context: OrchestratorRunContext) -> dict[str, Any]:
    return {"items": [dict(item) for item in run_context.fulfillment_items]}


def mark_plan_fulfillment(
    run_context: OrchestratorRunContext,
    tasks: Sequence[SubTask],
) -> None:
    if not run_context.fulfillment_items:
        return
    if _has_item(run_context, "multi_agent"):
        agents = _implementation_agent_ids(tasks)
        if len(agents) >= 2:
            _satisfy(run_context, "multi_agent", f"Planned work across {len(agents)} agents.")
        else:
            _pending(run_context, "multi_agent", "Planner did not assign multiple agents yet.")
    if _has_item(run_context, "review") and _has_independent_review(tasks):
        _pending(run_context, "review", "Plan includes an independent review task.")


def mark_task_fulfillment(
    run_context: OrchestratorRunContext,
    tasks: Sequence[SubTask],
    task_states: Mapping[str, TaskState],
) -> None:
    if not run_context.fulfillment_items:
        return
    successful_results = [
        run_context.results[task.task_id]
        for task in tasks
        if task_states.get(task.task_id) == TaskState.SUCCEEDED
        and task.task_id in run_context.results
    ]
    successful_attempts = [
        result.attempts[-1] for result in successful_results if result.attempts
    ]
    artifacts = {
        path
        for attempt in successful_attempts
        for path in [*attempt.artifact_paths, *attempt.file_changes.get("created", [])]
    }
    changed = {
        path
        for attempt in successful_attempts
        for path in [
            *attempt.file_changes.get("created", []),
            *attempt.file_changes.get("modified", []),
        ]
    }
    successful_agents = {
        attempt.agent_id for attempt in successful_attempts if attempt.agent_id != "orchestrator"
    }
    if _has_item(run_context, "document") and _has_any_path(artifacts, (".md", ".doc", ".docx")):
        _satisfy(run_context, "document", "Document artifact was generated.")
    code_paths = {*artifacts, *changed}
    if _has_item(run_context, "code_artifacts") and _has_any_path(
        code_paths,
        (".html", ".css", ".js", ".py", ".ts", ".tsx"),
    ):
        _satisfy(run_context, "code_artifacts", "Code artifacts were generated.")
    if _has_item(run_context, "multi_agent") and len(successful_agents) >= 2:
        _satisfy(
            run_context,
            "multi_agent",
            f"Completed attempts used {len(successful_agents)} agents.",
        )
    if _has_item(run_context, "review") and _review_satisfied(tasks, task_states, run_context):
        _satisfy(run_context, "review", "Independent review completed.")
    if _has_item(run_context, "diff") and (
        _has_any_path(artifacts, ("diff.md", ".diff", ".patch")) or len(changed) >= 2
    ):
        _satisfy(run_context, "diff", "Workspace changes/diff evidence is available.")
    _fail_unmet_terminal_items(run_context)


def mark_tool_fulfillment(
    run_context: OrchestratorRunContext,
    tool_name: str,
    result_status: str,
    output: str,
) -> None:
    if not run_context.fulfillment_items:
        return
    ok = result_status == "ok"
    lowered_output = output.lower()
    if tool_name == "start_workspace_preview":
        _set_platform_item(
            run_context,
            "preview",
            ok,
            "Workspace preview started.",
            output,
        )
    elif tool_name == "verify_web_preview":
        passed = ok and '"passed": true' in lowered_output
        _set_platform_item(
            run_context,
            "browser_verify",
            passed,
            "Browser verification passed.",
            output,
        )
    elif tool_name == "create_deployment":
        success = ok and any(
            marker in lowered_output
            for marker in ('"status": "published"', '"status":"published"', '"status": "running"')
        )
        _set_platform_item(
            run_context,
            "deployment",
            success,
            "Deployment was created.",
            output,
        )
    elif tool_name == "package_workspace_source":
        success = ok and "error" not in lowered_output
        _set_platform_item(
            run_context,
            "source_package",
            success,
            "Workspace source package was created.",
            output,
        )


def fulfillment_needs_attention(run_context: OrchestratorRunContext) -> list[str]:
    lines: list[str] = []
    for item in run_context.fulfillment_items:
        item_id = str(item.get("id") or "")
        if item_id in {"preview", "browser_verify", "deployment", "source_package"}:
            continue
        status = item.get("status")
        if status not in {"pending", "failed", "skipped"}:
            continue
        label = str(item.get("label") or item.get("id") or "requirement")
        reason = str(item.get("reason") or _default_reason(item_id))
        lines.append(f"{label}: {reason}")
    return lines


def _items_for_request(user_request: str) -> list[dict[str, Any]]:
    specs = [
        ("document", DOC_RE, "生成文档"),
        ("code_artifacts", CODE_RE, "生成代码产物"),
        ("multi_agent", MULTI_AGENT_RE, "多智能体分工"),
        ("review", REVIEW_RE, "审阅/复核"),
        ("preview", PREVIEW_RE, "网页预览"),
        ("browser_verify", BROWSER_RE, "浏览器质量验收"),
        ("deployment", DEPLOY_RE, "部署/发布"),
        ("diff", DIFF_RE, "Diff / 变更说明"),
        ("source_package", SOURCE_RE, "源码打包"),
    ]
    items: list[dict[str, Any]] = []
    for item_id, pattern, label in specs:
        if pattern.search(user_request):
            if item_id == "document" and _document_requirement_negated(user_request):
                continue
            items.append(
                {
                    "id": item_id,
                    "label": label,
                    "status": "pending",
                    "evidence": [],
                    "reason": None,
                }
            )
    return items


def _document_requirement_negated(user_request: str) -> bool:
    if DOCUMENT_FILE_RE.search(user_request):
        return False
    return bool(NEGATED_DOCUMENT_RE.search(user_request))


def _implementation_agent_ids(tasks: Sequence[SubTask]) -> set[str]:
    return {
        task.agent_id
        for task in tasks
        if task.agent_id != "orchestrator" and task.task_type == "implementation"
    }


def _has_independent_review(tasks: Sequence[SubTask]) -> bool:
    task_agents = {task.task_id: task.agent_id for task in tasks}
    for task in tasks:
        if task.task_type != "review":
            continue
        reviewed = task.review_of or task.depends_on
        if reviewed and all(task_agents.get(task_id) != task.agent_id for task_id in reviewed):
            return True
    return False


def _review_satisfied(
    tasks: Sequence[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext,
) -> bool:
    task_agents = {
        task.task_id: _final_agent_id(task, run_context) or task.agent_id for task in tasks
    }
    for task in tasks:
        if task.task_type != "review" or task_states.get(task.task_id) != TaskState.SUCCEEDED:
            continue
        result = run_context.results.get(task.task_id)
        if task.expected_output and not _result_has_expected_review_artifact(
            result,
            task.expected_output,
        ):
            continue
        review_agent = _final_agent_id(task, run_context) or task.agent_id
        reviewed = task.review_of or task.depends_on
        if not reviewed:
            return True
        if all(task_agents.get(task_id) != review_agent for task_id in reviewed):
            return True
    return False


def _result_has_expected_review_artifact(
    result: Any | None,
    expected_output: str,
) -> bool:
    if result is None or not result.attempts:
        return False
    expected_paths = _expected_output_paths(expected_output)
    artifact_paths = {
        path.lower()
        for attempt in result.attempts
        for path in [
            *attempt.artifact_paths,
            *attempt.file_changes.get("created", []),
            *attempt.file_changes.get("modified", []),
        ]
    }
    if expected_paths:
        return any(path.lower() in artifact_paths for path in expected_paths)
    return any(path.endswith(".md") and "review" in path for path in artifact_paths)


def _expected_output_paths(expected_output: str) -> set[str]:
    paths: set[str] = set()
    for token in re.findall(r"[\w./-]+", expected_output):
        normalized = token.strip("./").lower()
        if normalized.endswith((".md", ".txt", ".json", ".html", ".css", ".js")):
            paths.add(normalized)
    return paths


def _final_agent_id(task: SubTask, run_context: OrchestratorRunContext) -> str | None:
    result = run_context.results.get(task.task_id)
    if result is None or not result.attempts:
        return None
    return result.attempts[-1].agent_id


def _has_any_path(paths: Iterable[str], suffixes: tuple[str, ...]) -> bool:
    lowered = {path.lower() for path in paths}
    for path in lowered:
        if any(path.endswith(suffix) for suffix in suffixes):
            return True
    return False


def _has_item(run_context: OrchestratorRunContext, item_id: str) -> bool:
    return any(item.get("id") == item_id for item in run_context.fulfillment_items)


def _pending(run_context: OrchestratorRunContext, item_id: str, reason: str) -> None:
    for item in run_context.fulfillment_items:
        if item.get("id") == item_id and item.get("status") == "pending":
            item["reason"] = reason


def _satisfy(run_context: OrchestratorRunContext, item_id: str, evidence: str) -> None:
    for item in run_context.fulfillment_items:
        if item.get("id") != item_id:
            continue
        item["status"] = "satisfied"
        item["reason"] = None
        item.setdefault("evidence", [])
        if evidence and evidence not in item["evidence"]:
            item["evidence"].append(evidence)


def _set_platform_item(
    run_context: OrchestratorRunContext,
    item_id: str,
    passed: bool,
    evidence: str,
    output: str,
) -> None:
    if not _has_item(run_context, item_id):
        return
    if passed:
        _satisfy(run_context, item_id, evidence)
        return
    for item in run_context.fulfillment_items:
        if item.get("id") == item_id and item.get("status") != "satisfied":
            item["status"] = "failed"
            item["reason"] = _short_output(output)


def _fail_unmet_terminal_items(run_context: OrchestratorRunContext) -> None:
    for item in run_context.fulfillment_items:
        if item.get("status") != "pending":
            continue
        item_id = str(item.get("id") or "")
        if item_id in {"preview", "browser_verify", "deployment", "source_package"}:
            item["reason"] = _default_reason(item_id)
        elif item_id in {"multi_agent", "review", "document", "code_artifacts", "diff"}:
            item["status"] = "failed"
            item["reason"] = _default_reason(item_id)


def _short_output(output: str) -> str:
    text = " ".join(str(output or "").replace("\x00", "").split())
    if not text:
        return "平台工具未返回成功结果。"
    if len(text) > 180:
        return f"{text[:180]}..."
    return text


def _default_reason(item_id: str) -> str:
    return {
        "document": "没有确认生成文档产物。",
        "code_artifacts": "没有确认生成代码产物。",
        "multi_agent": "没有确认多个智能体实际参与完成。",
        "review": "没有确认独立审阅完成。",
        "preview": "尚未完成平台预览。",
        "browser_verify": "尚未完成浏览器级验收。",
        "deployment": "尚未完成平台部署。",
        "diff": "没有确认 Diff / 变更说明。",
        "source_package": "尚未完成源码打包。",
    }.get(item_id, "该要求尚未确认完成。")
