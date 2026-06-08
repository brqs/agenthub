"""Repair task discovery and instruction helpers for quality gates."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.agents.orchestrator._internal.presentation_markers import (
    sanitize_presentation_trace_value,
    tool_trace_presentation,
)
from app.agents.orchestrator.tools import OrchestratorToolResult, available_agent_ids
from app.agents.types import StreamChunk
from app.core.config import settings

SKIP_DIR_NAMES = {".agenthub", ".git", ".venv", "__pycache__", "node_modules"}
DEFAULT_REQUIRED_TEXT = ["任务", "代码", "Diff", "预览"]
PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]


def find_preview_entry(workspace_path: Path) -> str | None:
    root = workspace_path.resolve()
    direct_index = root / "index.html"
    if direct_index.is_file():
        return "index.html"

    candidates: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".htm"}:
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIR_NAMES or part.startswith(".env") for part in relative.parts):
            continue
        candidates.append(relative)

    index_candidates = [path for path in candidates if path.name.lower() == "index.html"]
    if len(index_candidates) == 1:
        return index_candidates[0].as_posix()
    if candidates:
        return candidates[0].as_posix()
    return None


def required_text(user_request: str) -> list[str]:
    required = list(DEFAULT_REQUIRED_TEXT)
    if re.search(r"(?i)button|按钮|交互", user_request):
        required.append("按钮")
    if re.search(r"移动端|mobile|viewport", user_request, re.I):
        required.append("移动")
    return required


def max_repair_rounds(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    configured = positive_int_config(
        config,
        "orchestrator_quality_max_repair_rounds",
        settings.orchestrator_quality_max_repair_rounds,
    )
    return max(0, min(configured, 5))


def repair_agent(config: Mapping[str, Any]) -> str | None:
    allowed = set(available_agent_ids(config))
    configured_order = config.get("orchestrator_quality_repair_agent_order")
    if isinstance(configured_order, list):
        order = [item for item in configured_order if isinstance(item, str)]
    else:
        order = [
            item.strip()
            for item in settings.orchestrator_quality_repair_agent_order.split(",")
            if item.strip()
        ]
    for agent_id in order:
        if agent_id in allowed:
            return agent_id
    return next(iter(sorted(allowed)), None)


def repair_instruction(
    entry_path: str,
    payload: dict[str, Any],
    raw_output: str,
) -> str:
    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []
    issue_text = truncate(
        json.dumps(issues[:20], ensure_ascii=False) if issues else raw_output,
        4000,
    )
    issue_codes = {
        item.get("code")
        for item in issues
        if isinstance(item, Mapping) and isinstance(item.get("code"), str)
    }
    mobile_overflow_guidance = ""
    if "mobile_no_horizontal_overflow" in issue_codes:
        mobile_overflow_guidance = (
            "\n特别修复 mobile_no_horizontal_overflow：添加全局 box-sizing；限制 "
            "html/body 和主容器 max-width:100% 与 overflow-x:hidden；让 grid/flex "
            "在移动端换行或改为单列；让 img/svg/video/canvas/table/pre/code/button "
            "不超过视口宽度，并对长文本使用 overflow-wrap:anywhere。"
        )
    return (
        "修复浏览器级质量验收失败的问题。只修改 workspace 内的静态前端文件，"
        "不要创建 server.js/package.json，不要启动服务。"
        f"\n入口 HTML: {entry_path}"
        "\n必须保持任务拆解、代码产物、Diff、网页预览、按钮交互和移动端适配可见。"
        "\n修复以下浏览器验证问题后，确保桌面和移动端都没有 JS 错误、资源错误或横向溢出："
        f"{mobile_overflow_guidance}"
        f"\n{issue_text}"
    )


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> StreamChunk:
    return StreamChunk(
        event_type="tool_call",
        agent_id="orchestrator",
        call_id=call_id,
        tool_name=name,
        tool_arguments=sanitize_presentation_trace_value(arguments),
        metadata={"presentation": tool_trace_presentation()},
    )


def tool_result(call_id: str, result: OrchestratorToolResult) -> StreamChunk:
    metadata: dict[str, Any] = {}
    if result.error_code:
        metadata["error_code"] = result.error_code
    return StreamChunk(
        event_type="tool_result",
        agent_id="orchestrator",
        call_id=call_id,
        tool_status="ok" if result.status == "ok" else "error",
        tool_output=sanitize_presentation_trace_value(result.output),
        tool_output_truncated=result.output_truncated,
        metadata=metadata or None,
    )


def error(error_code: str, message: str) -> StreamChunk:
    return StreamChunk(
        event_type="error",
        agent_id="orchestrator",
        error_code=error_code,
        error=truncate(message, 2000),
    )


def json_output(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def json_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "...[truncated]"
