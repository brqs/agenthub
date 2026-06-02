"""Deterministic preview quality gate for Orchestrator frontend tasks."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from app.agents.orchestrator.tools import OrchestratorToolResult, available_agent_ids
from app.agents.orchestrator.types import OrchestratorRunContext, SubTask
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.config import settings

DEPLOY_INTENT_RE = re.compile(
    r"(?i)(部署|发布|上线|端口|preview\s+(?:on|at|to)|deploy(?:ed|ment)?|port\s*\d{2,5})"
)
RELEASE_INTENT_RE = re.compile(r"(?i)(部署|发布|上线|deploy(?:ed|ment)?)")
SOURCE_EXPORT_INTENT_RE = re.compile(r"(?i)(源码|源代码|打包|下载|source|zip)")
CONTAINER_INTENT_RE = re.compile(r"(?i)(容器|容器化|docker|container)")
FRONTEND_INTENT_RE = re.compile(r"(?i)(前端|网页|页面|html|css|javascript|js|frontend|web)")
BROWSER_VERIFY_INTENT_RE = re.compile(
    r"(?i)(浏览器|质量验收|移动端|按钮|交互|browser|quality|viewport|mobile)"
)
REQUESTED_PORT_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")
SKIP_DIR_NAMES = {".agenthub", ".git", ".venv", "__pycache__", "node_modules"}
DEFAULT_REQUIRED_TEXT = ["任务", "代码", "Diff", "预览"]

TextBlockWithNext = Callable[[int, str], Iterable[tuple[StreamChunk, int]]]
PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]


class RunTaskWithPrefix(Protocol):
    def __call__(
        self,
        config: Mapping[str, Any],
        task: SubTask,
        messages: list[ChatMessage],
        next_block_index: int,
        run_context: OrchestratorRunContext,
        workspace_path: Path | None,
        tool_specs: list[ToolSpec] | None,
        *,
        call_id_prefix: str | None = None,
    ) -> AsyncIterator[tuple[StreamChunk, int]]: ...


async def run_quality_gate(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    run_context: OrchestratorRunContext,
    *,
    run_task: RunTaskWithPrefix,
    text_block_with_next: TextBlockWithNext,
    positive_int_config: PositiveIntConfig,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    """Run platform preview and browser verification for frontend deploy requests."""

    user_request = _latest_user_request(messages)
    if not _should_run_quality_gate(user_request):
        return
    executor = config.get("orchestrator_platform_tool_executor")
    if executor is None:
        return
    if workspace_path is None:
        yield _error("workspace_missing", "workspace_path is required"), next_block_index
        return

    max_rounds = _max_repair_rounds(config, positive_int_config)
    required_text = _required_text(user_request)
    repair_round = 0
    entry_path = _find_preview_entry(workspace_path)
    while entry_path is None and repair_round < max_rounds:
        repair_agent = _repair_agent(config)
        if repair_agent is None:
            yield (
                _error("browser_verification_failed", "no repair agent is available"),
                next_block_index,
            )
            return
        repair_round += 1
        repair_task = SubTask(
            task_id=f"quality-repair-{repair_round}",
            agent_id=repair_agent,
            title=f"Create missing frontend artifacts round {repair_round}",
            instruction=_repair_instruction(
                "index.html",
                {
                    "issues": [
                        "No HTML entry file was found. Create index.html, styles.css, "
                        "and app.js at the workspace root with the required task "
                        "breakdown, code artifact, Diff, webpage preview, button "
                        "interaction, and mobile adaptation sections."
                    ]
                },
                "no HTML entry file was found in the workspace",
            ),
            expected_output="index.html\nstyles.css\napp.js",
            include_history=True,
            priority=1000 + repair_round,
        )
        async for chunk, updated_block_index in run_task(
            config,
            repair_task,
            messages,
            next_block_index,
            run_context,
            workspace_path,
            tool_specs,
            call_id_prefix=f"quality-repair-{repair_round}",
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index
        entry_path = _find_preview_entry(workspace_path)

    preview_call_id = "orch.quality.preview"
    preview_args: dict[str, Any] = {"mode": "static"}
    if entry_path:
        preview_args["entry_path"] = entry_path
    requested_port = _requested_port(user_request)
    if requested_port is not None:
        preview_args["requested_port"] = requested_port

    yield _tool_call(preview_call_id, "start_workspace_preview", preview_args), next_block_index
    if entry_path is None:
        result = OrchestratorToolResult(
            status="error",
            output=_json_output(
                {"status": "error", "error": "no HTML entry file was found in the workspace"}
            ),
            error_code="preview_entry_not_found",
        )
    else:
        result = await executor("start_workspace_preview", preview_args)
    yield _tool_result(preview_call_id, result), next_block_index
    if result.status != "ok":
        yield _error("workspace_preview_start_failed", result.output), next_block_index
        return

    preview_payload = _json_payload(result.output)
    preview_url = _optional_str(preview_payload.get("url"))
    for chunk, updated_block_index in text_block_with_next(
        next_block_index,
        f"Platform preview deployed: {preview_url or '(unknown url)'}\n",
    ):
        next_block_index = updated_block_index
        yield chunk, updated_block_index
    if preview_url:
        yield StreamChunk(
            event_type="block_start",
            block_index=next_block_index,
            block_type="web_preview",
            metadata={
                "url": preview_url,
                "title": f"Workspace preview: {entry_path}",
                "description": "AgentHub platform-managed static preview.",
            },
        ), next_block_index + 1
        yield (
            StreamChunk(event_type="block_end", block_index=next_block_index),
            next_block_index + 1,
        )
        next_block_index += 1

    preview_refresh_needed = False
    while True:
        if preview_refresh_needed:
            entry_path = _find_preview_entry(workspace_path) or entry_path
            if entry_path:
                preview_args["entry_path"] = entry_path
            refresh_call_id = f"orch.quality.preview.refresh.{repair_round}"
            yield (
                _tool_call(refresh_call_id, "start_workspace_preview", preview_args),
                next_block_index,
            )
            refresh_result = await executor("start_workspace_preview", preview_args)
            yield _tool_result(refresh_call_id, refresh_result), next_block_index
            if refresh_result.status != "ok":
                yield (
                    _error("workspace_preview_start_failed", refresh_result.output),
                    next_block_index,
                )
                return
            preview_refresh_needed = False

        verify_call_id = f"orch.quality.verify.{repair_round + 1}"
        verify_args = {
            "required_text": required_text,
            "viewports": ["desktop", "mobile"],
            "click_buttons": True,
            "max_clicks": 5,
        }
        yield _tool_call(verify_call_id, "verify_web_preview", verify_args), next_block_index
        verify_result = await executor("verify_web_preview", verify_args)
        yield _tool_result(verify_call_id, verify_result), next_block_index
        verify_payload = _json_payload(verify_result.output)
        if verify_result.status == "ok" and verify_payload.get("passed") is True:
            async for chunk, updated_block_index in _run_deployment_tools(
                executor=executor,
                user_request=user_request,
                entry_path=entry_path,
                requested_port=requested_port,
                next_block_index=next_block_index,
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                "Browser quality verification passed.\n",
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
            return

        if repair_round >= max_rounds:
            yield _error("browser_verification_failed", verify_result.output), next_block_index
            return

        repair_agent = _repair_agent(config)
        if repair_agent is None:
            yield (
                _error("browser_verification_failed", "no repair agent is available"),
                next_block_index,
            )
            return

        repair_round += 1
        repair_task = SubTask(
            task_id=f"quality-repair-{repair_round}",
            agent_id=repair_agent,
            title=f"Repair browser quality issues round {repair_round}",
            instruction=_repair_instruction(
                entry_path or "index.html",
                verify_payload,
                verify_result.output,
            ),
            expected_output=entry_path,
            include_history=True,
            priority=1000 + repair_round,
        )
        async for chunk, updated_block_index in run_task(
            config,
            repair_task,
            messages,
            next_block_index,
            run_context,
            workspace_path,
            tool_specs,
            call_id_prefix=f"quality-repair-{repair_round}",
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index
        preview_refresh_needed = True


def _should_run_quality_gate(user_request: str) -> bool:
    if not user_request:
        return False
    wants_preview = bool(DEPLOY_INTENT_RE.search(user_request))
    wants_browser = bool(BROWSER_VERIFY_INTENT_RE.search(user_request))
    is_frontend = bool(FRONTEND_INTENT_RE.search(user_request))
    return is_frontend and (wants_preview or wants_browser)


def _latest_user_request(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _requested_port(text: str) -> int | None:
    match = REQUESTED_PORT_RE.search(text)
    if match is None:
        return None
    port = int(match.group(1))
    if 1 <= port <= 65535:
        return port
    return None


async def _run_deployment_tools(
    *,
    executor: Any,
    user_request: str,
    entry_path: str | None,
    requested_port: int | None,
    next_block_index: int,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    if RELEASE_INTENT_RE.search(user_request) and entry_path:
        args: dict[str, Any] = {
            "kind": "static_site",
            "entry_path": entry_path,
        }
        if requested_port is not None:
            args["requested_port"] = requested_port
        async for item in _call_deployment_tool(
            executor,
            "orch.deployment.static_site",
            "create_deployment",
            args,
            next_block_index,
        ):
            chunk, next_block_index = item
            yield chunk, next_block_index

    if SOURCE_EXPORT_INTENT_RE.search(user_request):
        async for item in _call_deployment_tool(
            executor,
            "orch.deployment.source_zip",
            "package_workspace_source",
            {"format": "zip"},
            next_block_index,
        ):
            chunk, next_block_index = item
            yield chunk, next_block_index

    if CONTAINER_INTENT_RE.search(user_request):
        async for item in _call_deployment_tool(
            executor,
            "orch.deployment.container",
            "create_deployment",
            {"kind": "container"},
            next_block_index,
        ):
            chunk, next_block_index = item
            yield chunk, next_block_index


async def _call_deployment_tool(
    executor: Any,
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    next_block_index: int,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    yield _tool_call(call_id, tool_name, arguments), next_block_index
    result = await executor(tool_name, arguments)
    yield _tool_result(call_id, result), next_block_index
    status_card = _deployment_status_card(result.output)
    if status_card is not None:
        yield StreamChunk(
            event_type="block_start",
            block_index=next_block_index,
            block_type="deployment_status",
            metadata=status_card,
        ), next_block_index + 1
        yield StreamChunk(
            event_type="block_end",
            block_index=next_block_index,
        ), next_block_index + 1


def _deployment_status_card(output: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    card = payload.get("status_card")
    if not isinstance(card, dict):
        return None
    if not isinstance(card.get("deployment_id"), str) or not card["deployment_id"]:
        return None
    return card


def _find_preview_entry(workspace_path: Path) -> str | None:
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


def _required_text(user_request: str) -> list[str]:
    required = list(DEFAULT_REQUIRED_TEXT)
    if re.search(r"(?i)button|按钮|交互", user_request):
        required.append("按钮")
    if re.search(r"移动端|mobile|viewport", user_request, re.I):
        required.append("移动")
    return required


def _max_repair_rounds(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    configured = positive_int_config(
        config,
        "orchestrator_quality_max_repair_rounds",
        settings.orchestrator_quality_max_repair_rounds,
    )
    return max(0, min(configured, 5))


def _repair_agent(config: Mapping[str, Any]) -> str | None:
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


def _repair_instruction(
    entry_path: str,
    payload: dict[str, Any],
    raw_output: str,
) -> str:
    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []
    issue_text = _truncate(
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


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> StreamChunk:
    return StreamChunk(
        event_type="tool_call",
        agent_id="orchestrator",
        call_id=call_id,
        tool_name=name,
        tool_arguments=arguments,
    )


def _tool_result(call_id: str, result: OrchestratorToolResult) -> StreamChunk:
    metadata: dict[str, Any] = {}
    if result.error_code:
        metadata["error_code"] = result.error_code
    return StreamChunk(
        event_type="tool_result",
        agent_id="orchestrator",
        call_id=call_id,
        tool_status="ok" if result.status == "ok" else "error",
        tool_output=result.output,
        tool_output_truncated=result.output_truncated,
        metadata=metadata or None,
    )


def _error(error_code: str, message: str) -> StreamChunk:
    return StreamChunk(
        event_type="error",
        agent_id="orchestrator",
        error_code=error_code,
        error=_truncate(message, 2000),
    )


def _json_output(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _json_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "...[truncated]"
