"""Follow-up evidence routing for Orchestrator conversations."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from app.agents.types import ChatMessage

ORCHESTRATOR_EVIDENCE_HEADER = "Orchestrator evidence pack:"

MAX_WORKSPACE_FILES = 50
MAX_FILE_SNIPPET_CHARS = 1200
MAX_TOTAL_SNIPPET_CHARS = 3000
MAX_CONTEXT_CHARS = 8000

_EVIDENCE_MARKERS = (
    "生成了吗",
    "生成了么",
    "做好了吗",
    "做好了么",
    "完成了吗",
    "完成了么",
    "做完了吗",
    "做完了么",
    "部署了吗",
    "部署了么",
    "发布了吗",
    "发布了么",
    "上线了吗",
    "上线了么",
    "预览地址",
    "预览链接",
    "预览能打开",
    "预览在哪里",
    "地址是什么",
    "链接是什么",
    "验收通过了吗",
    "验收通过了么",
    "改了哪些文件",
    "修改了哪些文件",
    "生成了哪些文件",
    "有哪些文件",
    "文件在哪",
    "文件在哪里",
    "diff在哪",
    "diff 在哪",
    "what files",
    "is it done",
    "did it finish",
    "preview url",
    "deployment url",
    "was it deployed",
    "validation passed",
)

_ACTION_MARKERS = (
    "继续",
    "继续完成",
    "继续部署",
    "帮我修复",
    "修复",
    "修改",
    "改成",
    "补齐",
    "补上",
    "重新",
    "再部署",
    "完善",
    "优化",
    "continue",
    "fix",
    "repair",
    "change",
    "update",
    "redeploy",
)

_FORBIDDEN_PATTERNS = (
    "ReAct step",
    "Observation:",
    "Action:",
    "Tools:",
    "result ok",
    "call_",
    "Traceback",
    "stderr",
    "external_runtime_error",
    "invalid_task_plan",
    "planner did not return",
    "approval:",
    "sandbox:",
    "workdir:",
    "/workspaces/",
    "/home/ubuntu/",
    "/root/.agenthub",
    ".claude.json",
    "claude-auth",
)


@dataclass(slots=True)
class EvidencePack:
    """Bounded facts from the latest Orchestrator run and workspace."""

    has_evidence: bool = False
    run_status: str | None = None
    run_request: str = ""
    run_summary: str = ""
    tasks: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    workspace_files: list[str] = field(default_factory=list)
    file_snippets: dict[str, str] = field(default_factory=dict)
    fulfillment: dict[str, str] = field(default_factory=dict)
    preview_status: str | None = None
    preview_url: str | None = None
    preview_entry_path: str | None = None
    preview_port: int | None = None
    deployments: list[dict[str, str]] = field(default_factory=list)
    evaluations: list[str] = field(default_factory=list)


def is_context_action_request(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(marker in normalized for marker in _ACTION_MARKERS)


def is_evidence_followup_request(text: str) -> bool:
    normalized = _normalize_text(text)
    if is_context_action_request(normalized):
        return False
    if any(marker in normalized for marker in _EVIDENCE_MARKERS):
        return True
    return bool(
        re.search(r"(生成|完成|做好|做完|部署|发布|预览|验收).{0,6}(?:了|好)[吗么]", normalized)
    )


async def evidence_answer_text(
    config: Mapping[str, Any],
    user_request: str,
    workspace_path: Path | None,
) -> str | None:
    if not is_evidence_followup_request(user_request):
        return None
    pack = await collect_evidence_pack(
        config,
        user_request,
        workspace_path,
        include_file_snippets=False,
    )
    return deterministic_evidence_answer(user_request, pack)


async def build_evidence_context_message(
    config: Mapping[str, Any],
    user_request: str,
    workspace_path: Path | None,
) -> ChatMessage | None:
    if not is_context_action_request(user_request):
        return None
    pack = await collect_evidence_pack(
        config,
        user_request,
        workspace_path,
        include_file_snippets=True,
    )
    if not pack.has_evidence:
        return None
    return ChatMessage(
        role="system",
        content=(
            f"{ORCHESTRATOR_EVIDENCE_HEADER}\n"
            "Use these bounded facts as background evidence for the latest user request. "
            "Do not expose raw internal details.\n"
            f"{format_evidence_pack(pack)}"
        ),
    )


async def context_action_answer_text(
    config: Mapping[str, Any],
    user_request: str,
    workspace_path: Path | None,
) -> str | None:
    """Answer continue-style requests when evidence shows no missing action remains."""

    if not is_context_action_request(user_request):
        return None
    normalized = _normalize_text(user_request)
    if not ("继续" in normalized and any(item in normalized for item in ("部署", "发布", "上线"))):
        return None
    pack = await collect_evidence_pack(
        config,
        user_request,
        workspace_path,
        include_file_snippets=False,
    )
    if not pack.has_evidence:
        return None
    deployment_done = pack.fulfillment.get("deployment") == "satisfied" or bool(
        _latest_deployment_url(pack)
    )
    if not deployment_done:
        return None
    lines = [
        "我查了一下，当前没有发现缺失的部署步骤；最近一次部署已有完成记录。",
        *(_deployment_answer_lines(pack) or _compact_status_lines(pack)),
    ]
    return _clean_visible_text("\n".join(_dedupe(lines))) + "\n"


def inject_evidence_context(
    messages: list[ChatMessage],
    evidence_message: ChatMessage | None,
) -> list[ChatMessage]:
    if evidence_message is None:
        return messages
    return [*messages, evidence_message]


async def collect_evidence_pack(
    config: Mapping[str, Any],
    user_request: str,
    workspace_path: Path | None,
    *,
    include_file_snippets: bool,
) -> EvidencePack:
    pack = EvidencePack()
    await _collect_run_evidence(config, pack)
    await _collect_platform_evidence(config, pack)
    _collect_workspace_evidence(
        workspace_path,
        pack,
        user_request=user_request,
        include_file_snippets=include_file_snippets,
    )
    pack.has_evidence = bool(
        pack.run_status
        or pack.tasks
        or pack.artifacts
        or pack.workspace_files
        or pack.preview_url
        or pack.deployments
        or pack.evaluations
        or pack.fulfillment
    )
    return pack


def deterministic_evidence_answer(user_request: str, pack: EvidencePack) -> str:
    if not pack.has_evidence:
        return "我没有在当前会话里找到最近 Orchestrator 运行、workspace 文件、预览或部署记录。"

    normalized = _normalize_text(user_request)
    lines: list[str] = []
    generated = _looks_generated(pack)
    if _asks_preview(normalized):
        lines.extend(_preview_answer_lines(pack))
    elif _asks_deployment(normalized):
        lines.extend(_deployment_answer_lines(pack))
    elif _asks_validation(normalized):
        lines.extend(_validation_answer_lines(pack))
    elif _asks_files(normalized):
        lines.extend(_file_answer_lines(pack))
    else:
        lines.append(
            "已生成。"
            if generated
            else "我找到了最近任务记录，但还不能确认全部生成完成。"
        )
        lines.extend(_compact_status_lines(pack))

    if not lines:
        lines.extend(_compact_status_lines(pack))
    return _clean_visible_text("\n".join(_dedupe(lines))) + "\n"


def format_evidence_pack(pack: EvidencePack) -> str:
    lines: list[str] = []
    if pack.run_status:
        lines.append(f"- latest_run_status: {pack.run_status}")
    if pack.run_request:
        lines.append(f"- latest_run_request: {_truncate(pack.run_request, 300)}")
    if pack.fulfillment:
        lines.append(
            "- fulfillment: "
            + ", ".join(f"{key}={value}" for key, value in pack.fulfillment.items())
        )
    if pack.tasks:
        lines.append("- tasks:")
        lines.extend(f"  - {item}" for item in pack.tasks[:8])
    if pack.artifacts or pack.changed_files:
        lines.append(
            "- files: "
            + ", ".join(_dedupe([*pack.artifacts, *pack.changed_files])[:20])
        )
    if pack.workspace_files:
        lines.append("- workspace_tree: " + ", ".join(pack.workspace_files[:MAX_WORKSPACE_FILES]))
    if pack.preview_url:
        lines.append(
            "- preview: "
            f"status={pack.preview_status or 'unknown'}, "
            f"port={pack.preview_port or 'unknown'}, "
            f"entry={pack.preview_entry_path or 'unknown'}, url={pack.preview_url}"
        )
    if pack.deployments:
        lines.append("- deployments:")
        lines.extend(
            "  - "
            + ", ".join(f"{key}={value}" for key, value in item.items() if value)
            for item in pack.deployments[:6]
        )
    if pack.evaluations:
        lines.append("- evaluations: " + ", ".join(pack.evaluations[:10]))
    if pack.file_snippets:
        lines.append("- selected_file_snippets:")
        for path, snippet in pack.file_snippets.items():
            lines.append(f"  - {path}: {_truncate(snippet, MAX_FILE_SNIPPET_CHARS)}")
    text = "\n".join(lines)
    return _clean_visible_text(_truncate(text, MAX_CONTEXT_CHARS))


async def _collect_run_evidence(config: Mapping[str, Any], pack: EvidencePack) -> None:
    db = config.get("orchestrator_db_session")
    conversation_id = _conversation_uuid(config.get("conversation_id"))
    if db is None or conversation_id is None:
        return
    try:
        from app.services.orchestrator_memory import (  # noqa: PLC0415
            get_orchestrator_run_detail,
            list_orchestrator_runs,
        )

        runs = await list_orchestrator_runs(db, conversation_id, limit=3)
        if not runs:
            return
        run = runs[0]
        detail = await get_orchestrator_run_detail(db, conversation_id, run.id)
        if detail is None:
            return
        run, tasks, attempts, events = detail
    except Exception:  # noqa: BLE001
        return

    pack.run_status = str(getattr(run, "status", "") or "")
    pack.run_request = _clean_visible_text(str(getattr(run, "user_request", "") or ""))
    pack.run_summary = _clean_visible_text(str(getattr(run, "final_summary", "") or ""))
    attempts_by_task: dict[str, list[Any]] = {}
    for attempt in attempts:
        attempts_by_task.setdefault(str(getattr(attempt, "task_id", "") or ""), []).append(
            attempt
        )
        pack.artifacts.extend(_safe_path_list(getattr(attempt, "artifact_paths", [])))
    for task in tasks[:8]:
        task_id = str(getattr(task, "task_id", "") or "")
        task_attempts = attempts_by_task.get(task_id, [])
        final_attempt = task_attempts[-1] if task_attempts else None
        agent_id = (
            str(getattr(final_attempt, "agent_id", "") or "")
            or str(getattr(task, "agent_id", "") or "")
            or "unknown"
        )
        state = _status_label(getattr(task, "final_state", "unknown"))
        title = _clean_visible_text(str(getattr(task, "title", "") or task_id))
        if title:
            pack.tasks.append(f"{state}: @{agent_id} {title}")
        for attempt in task_attempts:
            file_changes = getattr(attempt, "file_changes", None)
            if isinstance(file_changes, Mapping):
                for key in ("created", "modified"):
                    pack.changed_files.extend(_safe_path_list(file_changes.get(key, [])))
    _collect_event_evidence(events, pack)
    pack.artifacts = _dedupe(pack.artifacts)
    pack.changed_files = _dedupe(pack.changed_files)


async def _collect_platform_evidence(config: Mapping[str, Any], pack: EvidencePack) -> None:
    db = config.get("orchestrator_db_session")
    conversation_id = _conversation_uuid(config.get("conversation_id"))
    if db is None or conversation_id is None:
        return
    try:
        from app.services.workspace_preview import WorkspacePreviewService  # noqa: PLC0415

        preview = await WorkspacePreviewService().get(db, conversation_id)
    except Exception:  # noqa: BLE001
        preview = None
    if preview is not None:
        pack.preview_status = str(getattr(preview, "status", "") or "")
        pack.preview_url = _http_url(getattr(preview, "url", None))
        pack.preview_entry_path = _safe_path(getattr(preview, "entry_path", None))
        port = getattr(preview, "port", None)
        pack.preview_port = int(port) if isinstance(port, int) else None
    try:
        from app.services.workspace_deployment import (  # noqa: PLC0415
            WorkspaceDeploymentService,
        )

        deployments = await WorkspaceDeploymentService().list(db, conversation_id)
    except Exception:  # noqa: BLE001
        deployments = []
    for item in deployments[:8]:
        summary = {
            "kind": str(getattr(item, "kind", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "entry": _safe_path(getattr(item, "entry_path", None)) or "",
            "url": _http_url(getattr(item, "url", None)) or "",
            "download_url": _http_url(getattr(item, "download_url", None)) or "",
            "healthcheck_url": _http_url(getattr(item, "healthcheck_url", None)) or "",
        }
        pack.deployments.append(summary)


def _collect_workspace_evidence(
    workspace_path: Path | None,
    pack: EvidencePack,
    *,
    user_request: str,
    include_file_snippets: bool,
) -> None:
    if workspace_path is None:
        return
    root = workspace_path.resolve()
    if not root.exists():
        return
    files: list[tuple[str, int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            continue
        if _skip_relative_path(relative):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        files.append((relative.as_posix(), size))
        if len(files) >= MAX_WORKSPACE_FILES:
            break
    pack.workspace_files = [f"{path} ({size} B)" for path, size in files]
    if include_file_snippets:
        _collect_file_snippets(root, [path for path, _size in files], user_request, pack)


def _collect_file_snippets(
    root: Path,
    files: Sequence[str],
    user_request: str,
    pack: EvidencePack,
) -> None:
    requested_names = {
        name.lower()
        for name in re.findall(r"[\w./-]+\.(?:md|txt|html|css|js|json|yaml|yml)", user_request)
    }
    candidates: list[str] = []
    for preferred in ("README.md", "planning.md", "index.html", "styles.css", "app.js"):
        if preferred in files:
            candidates.append(preferred)
    candidates.extend(path for path in files if path.lower() in requested_names)
    total = 0
    for relative in _dedupe(candidates):
        if total >= MAX_TOTAL_SNIPPET_CHARS:
            break
        path = root / relative
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        snippet = content[:MAX_FILE_SNIPPET_CHARS]
        total += len(snippet)
        pack.file_snippets[relative] = _clean_visible_text(snippet)


def _collect_event_evidence(events: Iterable[Any], pack: EvidencePack) -> None:
    fulfillment: dict[str, str] = {}
    evaluations: list[str] = []
    for event in events:
        event_type = str(getattr(event, "event_type", "") or "")
        payload = getattr(event, "payload", None)
        if not isinstance(payload, Mapping):
            continue
        if event_type == "command_fulfillment_status":
            for item in payload.get("items", []):
                if not isinstance(item, Mapping):
                    continue
                item_id = str(item.get("id") or "")
                status = str(item.get("status") or "")
                if not item_id or not status:
                    continue
                if fulfillment.get(item_id) == "satisfied":
                    continue
                fulfillment[item_id] = status
        elif event_type == "evaluation_result":
            for result in payload.get("results", []):
                if not isinstance(result, Mapping):
                    continue
                evaluator = str(result.get("evaluator") or "")
                status = str(result.get("status") or "")
                if evaluator and status:
                    evaluations.append(f"{evaluator}={status}")
    pack.fulfillment = fulfillment
    pack.evaluations = _dedupe(evaluations)


def _compact_status_lines(pack: EvidencePack) -> list[str]:
    lines: list[str] = []
    if pack.run_status:
        lines.append(f"最近一次 Orchestrator 任务状态：{_status_label(pack.run_status)}。")
    if pack.run_request:
        lines.append(f"最近任务：{_truncate(pack.run_request, 300)}")
    if pack.tasks:
        lines.append("执行结果：" + "；".join(pack.tasks[:5]) + "。")
    output_files = _current_workspace_paths(pack) or _dedupe(
        [*pack.artifacts, *pack.changed_files]
    )
    if output_files:
        lines.append("任务产物：" + "、".join(output_files[:10]) + "。")
    if pack.fulfillment:
        satisfied = [
            _fulfillment_label(key)
            for key, value in pack.fulfillment.items()
            if value == "satisfied"
        ]
        pending = [
            _fulfillment_label(key)
            for key, value in pack.fulfillment.items()
            if value != "satisfied"
        ]
        if satisfied:
            lines.append("已满足：" + "、".join(satisfied) + "。")
        if pending:
            lines.append("仍需确认：" + "、".join(pending) + "。")
    if pack.workspace_files:
        files = [item.split(" (", 1)[0] for item in pack.workspace_files[:10]]
        lines.append("当前 workspace 文件：" + "、".join(files) + "。")
    if pack.preview_url:
        lines.append(f"预览：{pack.preview_url}")
    deployment_url = _latest_deployment_url(pack)
    if deployment_url:
        lines.append(f"部署：{deployment_url}")
    if pack.evaluations:
        lines.append("验收记录：" + "、".join(pack.evaluations[:5]) + "。")
    return lines


def _preview_answer_lines(pack: EvidencePack) -> list[str]:
    if pack.preview_url:
        return [
            "预览已经有记录。",
            f"预览地址：{pack.preview_url}",
            (
                f"状态：{_status_label(pack.preview_status or 'unknown')}；"
                f"入口：{pack.preview_entry_path or '未记录'}；"
                f"端口：{pack.preview_port or '未记录'}。"
            ),
        ]
    return ["我没有找到当前会话的 workspace preview 记录。", *_compact_status_lines(pack)]


def _deployment_answer_lines(pack: EvidencePack) -> list[str]:
    if not pack.deployments:
        return ["我没有找到当前会话的部署记录。", *_compact_status_lines(pack)]
    lines = ["我找到了部署记录："]
    for item in pack.deployments[:5]:
        kind = _deployment_kind_label(item.get("kind", ""))
        status = _status_label(item.get("status", ""))
        url = item.get("url") or item.get("download_url") or item.get("healthcheck_url") or ""
        suffix = f"：{url}" if url else ""
        lines.append(f"- {kind} {status}{suffix}")
    return lines


def _validation_answer_lines(pack: EvidencePack) -> list[str]:
    passed = any(
        "browser_preview_quality=passed" in item or "deployment_health=passed" in item
        for item in pack.evaluations
    ) or pack.fulfillment.get("browser_verify") == "satisfied"
    if passed:
        return ["浏览器级验收已有通过记录。", *_compact_status_lines(pack)]
    if pack.evaluations:
        return ["我找到了验收记录：", *[f"- {item}" for item in pack.evaluations[:8]]]
    return ["我没有找到浏览器级验收通过记录。", *_compact_status_lines(pack)]


def _file_answer_lines(pack: EvidencePack) -> list[str]:
    files = _current_workspace_paths(pack) or _dedupe([*pack.artifacts, *pack.changed_files])
    if not files:
        return ["我没有找到当前 workspace 文件记录。", *_compact_status_lines(pack)]
    return ["当前能确认的文件包括：", *[f"- {path}" for path in files[:20]]]


def _current_workspace_paths(pack: EvidencePack) -> list[str]:
    return _dedupe(
        item.split(" (", 1)[0]
        for item in pack.workspace_files
        if isinstance(item, str) and item.strip()
    )


def _looks_generated(pack: EvidencePack) -> bool:
    if pack.run_status in {"done", "succeeded"} and (
        pack.artifacts or pack.changed_files or pack.workspace_files
    ):
        return True
    if pack.fulfillment.get("code_artifacts") == "satisfied":
        return True
    return bool(pack.workspace_files and any("index.html" in item for item in pack.workspace_files))


def _latest_deployment_url(pack: EvidencePack) -> str | None:
    for item in pack.deployments:
        if item.get("status") == "published" and item.get("url"):
            return item["url"]
    return None


def _asks_preview(text: str) -> bool:
    return any(marker in text for marker in ("预览", "preview", "地址是什么", "链接是什么"))


def _asks_deployment(text: str) -> bool:
    return any(marker in text for marker in ("部署", "发布", "上线", "deployment", "deployed"))


def _asks_validation(text: str) -> bool:
    return any(marker in text for marker in ("验收", "浏览器", "质量", "validation", "passed"))


def _asks_files(text: str) -> bool:
    return any(
        marker in text
        for marker in ("文件", "diff", "改了哪些", "修改了哪些", "what files")
    )


def _conversation_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _normalize_text(text: str) -> str:
    return (
        str(text or "")
        .replace("@orchestrator", "")
        .replace("＠orchestrator", "")
        .strip()
        .lower()
    )


def _clean_visible_text(text: str) -> str:
    clean = str(text or "").replace("\x00", "")
    clean = re.sub(r"/(?:workspaces|home/ubuntu|root/\.agenthub)/\S+", "[内部路径]", clean)
    clean = re.sub(r"call_[A-Za-z0-9_-]+", "工具调用", clean)
    for forbidden in _FORBIDDEN_PATTERNS:
        clean = clean.replace(forbidden, "[内部信息]")
    return " ".join(clean.split()) if "\n" not in clean else "\n".join(
        " ".join(line.split()) for line in clean.splitlines()
    )


def _safe_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = value.strip().replace("\\", "/")
    if path.startswith("/") or ".." in Path(path).parts:
        return None
    return path[:240]


def _safe_path_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value:
        path = _safe_path(item)
        if path:
            paths.append(path)
    return paths


def _skip_relative_path(relative: Path) -> bool:
    excluded = {".git", ".agenthub", "node_modules", ".venv", "__pycache__"}
    return any(part in excluded or part.startswith(".") for part in relative.parts)


def _http_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    if url.startswith("http://") or url.startswith("https://") or url.startswith("/api/"):
        return url
    return None


def _status_label(value: object) -> str:
    status = str(value or "unknown").lower()
    return {
        "done": "已完成",
        "succeeded": "已完成",
        "passed": "通过",
        "published": "已发布",
        "running": "运行中",
        "queued": "排队中",
        "publishing": "发布中",
        "not_supported": "暂不支持",
        "error": "失败",
        "failed": "失败",
        "pending": "待确认",
        "skipped": "已跳过",
        "unknown": "未知",
    }.get(status, status)


def _fulfillment_label(item_id: str) -> str:
    return {
        "document": "文档",
        "code_artifacts": "代码产物",
        "multi_agent": "多智能体分工",
        "review": "审阅",
        "preview": "预览",
        "browser_verify": "浏览器验收",
        "deployment": "部署",
        "diff": "Diff",
        "source_package": "源码打包",
    }.get(item_id, item_id)


def _deployment_kind_label(kind: str) -> str:
    return {
        "static_site": "静态站点",
        "source_zip": "源码包",
        "container": "容器部署",
    }.get(kind, kind or "部署")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
