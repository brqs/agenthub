"""Deterministic preview quality gate for Orchestrator frontend tasks."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from app.agents.orchestrator.evaluation import (
    EvaluationIssue,
    EvaluationResult,
    ReflectionResult,
    evaluation_results_payload,
    reflection_payload,
)
from app.agents.orchestrator.memory_hooks import record_event as _memory_record_event
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
    """Run the browser_preview_quality evaluator for frontend deploy requests."""

    user_request = _latest_user_request(messages)
    if not _should_run_quality_gate(user_request):
        return
    executor = config.get("orchestrator_platform_tool_executor")
    if executor is None:
        return
    if workspace_path is None:
        await _record_evaluation_failure(
            config,
            run_context,
            "browser_preview_quality",
            "workspace_missing",
            "workspace_path is required",
            repair_hint="Run the Orchestrator with a workspace path before preview verification.",
        )
        yield _error("workspace_missing", "workspace_path is required"), next_block_index
        return

    await _record_evaluation_started(
        config,
        run_context,
        "browser_preview_quality",
        {"requested_port": _requested_port(user_request)},
    )
    max_rounds = _max_repair_rounds(config, positive_int_config)
    required_text = _required_text(user_request)
    repair_round = 0
    entry_path = _find_preview_entry(workspace_path)
    while entry_path is None and repair_round < max_rounds:
        repair_agent = _repair_agent(config)
        if repair_agent is None:
            await _record_evaluation_failure(
                config,
                run_context,
                "browser_preview_quality",
                "repair_agent_missing",
                "no repair agent is available",
                repair_hint="Configure a quality repair agent or create the missing HTML artifact.",
            )
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
        await _record_evaluation_failure(
            config,
            run_context,
            "browser_preview_quality",
            result.error_code or "workspace_preview_start_failed",
            result.output,
            checked_artifacts=[entry_path] if entry_path else [],
            repair_hint="Fix the preview entry artifact and retry start_workspace_preview.",
        )
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
                await _record_evaluation_failure(
                    config,
                    run_context,
                    "browser_preview_quality",
                    refresh_result.error_code or "workspace_preview_start_failed",
                    refresh_result.output,
                    checked_artifacts=[entry_path] if entry_path else [],
                    repair_hint="Fix the preview entry artifact and retry start_workspace_preview.",
                )
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
            await _record_evaluation_result(
                config,
                run_context,
                EvaluationResult(
                    evaluator="browser_preview_quality",
                    status="passed",
                    passed=True,
                    checked_artifacts=[entry_path] if entry_path else [],
                    issues=[
                        EvaluationIssue(
                            code="browser_verification_passed",
                            message="verify_web_preview passed for desktop and mobile.",
                            evidence=preview_url,
                        )
                    ],
                ),
            )
            deployment_result: EvaluationResult | None = None
            deployment_repair_round = 0
            while True:
                deployment_tool_results: list[
                    tuple[str, dict[str, Any], OrchestratorToolResult]
                ] = []
                call_id_suffix = (
                    "" if deployment_repair_round == 0 else f".retry.{deployment_repair_round}"
                )
                async for chunk, updated_block_index in _run_deployment_tools(
                    executor=executor,
                    user_request=user_request,
                    entry_path=entry_path,
                    requested_port=requested_port,
                    next_block_index=next_block_index,
                    deployment_tool_results=deployment_tool_results,
                    call_id_suffix=call_id_suffix,
                ):
                    next_block_index = updated_block_index
                    yield chunk, updated_block_index
                deployment_result = _deployment_health_result(
                    user_request,
                    deployment_tool_results,
                )
                if deployment_result is None:
                    break
                repairable = _deployment_result_repairable(deployment_result)
                reflection = (
                    _deployment_reflection(
                        deployment_result,
                        deployment_tool_results,
                        deployment_repair_round,
                    )
                    if not deployment_result.passed and repairable
                    else None
                )
                await _record_evaluation_started(
                    config,
                    run_context,
                    "deployment_health",
                    {
                        "tool_count": len(deployment_tool_results),
                        "repair_round": deployment_repair_round,
                    },
                )
                await _record_evaluation_result(
                    config,
                    run_context,
                    deployment_result,
                    reflection,
                )
                if deployment_result.passed or not repairable:
                    break
                if deployment_repair_round >= max_rounds:
                    break
                repair_agent = _repair_agent(config)
                if repair_agent is None:
                    break
                deployment_repair_round += 1
                repair_task = SubTask(
                    task_id=f"deployment-repair-{deployment_repair_round}",
                    agent_id=repair_agent,
                    title=f"Repair deployment issues round {deployment_repair_round}",
                    instruction=(
                        reflection.repair_instruction
                        if reflection is not None
                        else "Repair the workspace deployment artifacts and retry deployment."
                    ),
                    expected_output=_deployment_repair_expected_output(
                        user_request,
                        entry_path,
                    ),
                    include_history=True,
                    priority=2000 + deployment_repair_round,
                )
                async for chunk, updated_block_index in run_task(
                    config,
                    repair_task,
                    messages,
                    next_block_index,
                    run_context,
                    workspace_path,
                    tool_specs,
                    call_id_prefix=f"deployment-repair-{deployment_repair_round}",
                ):
                    next_block_index = updated_block_index
                    yield chunk, updated_block_index
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                _quality_passed_text(deployment_result, deployment_repair_round),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
            return

        if repair_round >= max_rounds:
            await _record_evaluation_failure(
                config,
                run_context,
                "browser_preview_quality",
                verify_result.error_code or "browser_verification_failed",
                verify_result.output,
                checked_artifacts=[entry_path] if entry_path else [],
                repair_hint="Repair the static frontend until verify_web_preview passes.",
            )
            yield _error("browser_verification_failed", verify_result.output), next_block_index
            return

        repair_agent = _repair_agent(config)
        if repair_agent is None:
            await _record_evaluation_failure(
                config,
                run_context,
                "browser_preview_quality",
                "repair_agent_missing",
                "no repair agent is available",
                checked_artifacts=[entry_path] if entry_path else [],
                repair_hint="Configure a quality repair agent or manually fix the browser issues.",
            )
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
    deployment_tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]]
    | None = None,
    call_id_suffix: str = "",
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
            f"orch.deployment.static_site{call_id_suffix}",
            "create_deployment",
            args,
            next_block_index,
            deployment_tool_results,
        ):
            chunk, next_block_index = item
            yield chunk, next_block_index

    if SOURCE_EXPORT_INTENT_RE.search(user_request):
        async for item in _call_deployment_tool(
            executor,
            f"orch.deployment.source_zip{call_id_suffix}",
            "package_workspace_source",
            {"format": "zip"},
            next_block_index,
            deployment_tool_results,
        ):
            chunk, next_block_index = item
            yield chunk, next_block_index

    if CONTAINER_INTENT_RE.search(user_request):
        async for item in _call_deployment_tool(
            executor,
            f"orch.deployment.container{call_id_suffix}",
            "create_deployment",
            {"kind": "container"},
            next_block_index,
            deployment_tool_results,
        ):
            chunk, next_block_index = item
            yield chunk, next_block_index


async def _call_deployment_tool(
    executor: Any,
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    next_block_index: int,
    deployment_tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]]
    | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    yield _tool_call(call_id, tool_name, arguments), next_block_index
    result = await executor(tool_name, arguments)
    if deployment_tool_results is not None:
        deployment_tool_results.append((tool_name, dict(arguments), result))
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


def _deployment_health_result(
    user_request: str,
    tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]],
) -> EvaluationResult | None:
    if not (
        RELEASE_INTENT_RE.search(user_request)
        or SOURCE_EXPORT_INTENT_RE.search(user_request)
        or CONTAINER_INTENT_RE.search(user_request)
    ):
        return None
    if not tool_results:
        return EvaluationResult(
            evaluator="deployment_health",
            status="failed",
            passed=False,
            severity="major",
            issues=[
                EvaluationIssue(
                    code="deployment_tool_not_called",
                    message="No deployment tool was called for a deployment request.",
                    repair_hint=(
                        "Call the required deployment/export platform tool after preview passes."
                    ),
                )
            ],
        )
    issues: list[EvaluationIssue] = []
    checked: list[str] = []
    for tool_name, arguments, result in tool_results:
        kind = str(arguments.get("kind") or tool_name)
        checked.append(kind)
        payload = _json_payload(result.output)
        status = payload.get("status")
        if result.status != "ok":
            issues.append(
                EvaluationIssue(
                    code="deployment_tool_error",
                    message=f"{tool_name} for {kind} returned an error.",
                    evidence=result.output,
                    repair_hint=(
                        "Fix the deployment input artifact and rerun the platform deployment tool."
                    ),
                )
            )
            continue
        if tool_name == "package_workspace_source":
            if status != "published" or not _optional_str(payload.get("download_url")):
                issues.append(
                    EvaluationIssue(
                        code="source_export_unhealthy",
                        message="Source package export did not publish a download URL.",
                        evidence=result.output,
                        repair_hint=(
                            "Ensure package_workspace_source returns a published source_zip "
                            "with download_url."
                        ),
                    )
                )
            continue
        if kind == "container" and status == "not_supported":
            issues.append(
                EvaluationIssue(
                    code="container_deployment_not_supported",
                    message="Container deployment is not supported by the current platform.",
                    evidence=result.output,
                    repair_hint=(
                        "Keep the static/source deployment healthy and document the "
                        "container limitation."
                    ),
                )
            )
            continue
        if kind == "container":
            if not _optional_str(payload.get("healthcheck_url")):
                issues.append(
                    EvaluationIssue(
                        code="container_health_unhealthy",
                        message="Container deployment did not publish a healthcheck URL.",
                        evidence=result.output,
                        repair_hint=(
                            "Fix the container app, Dockerfile, exposed port, or health route "
                            "until the platform health check passes."
                        ),
                    )
                )
            if payload.get("runtime_status") != "running":
                issues.append(
                    EvaluationIssue(
                        code="container_health_unhealthy",
                        message="Container runtime is not running after deployment.",
                        evidence=result.output,
                        repair_hint=(
                            "Fix container startup and health behavior, then redeploy."
                        ),
                    )
                )
        if status != "published" or not _optional_str(payload.get("url")):
            issues.append(
                EvaluationIssue(
                    code="deployment_not_published",
                    message=f"{kind} deployment is not published with a URL.",
                    evidence=result.output,
                    repair_hint=(
                        "Fix the deployment artifact until create_deployment returns "
                        "published with url."
                    ),
                )
            )
    return EvaluationResult(
        evaluator="deployment_health",
        status="failed" if issues else "passed",
        passed=not issues,
        severity="major" if issues else "info",
        issues=issues,
        checked_artifacts=checked,
    )


def _deployment_result_repairable(result: EvaluationResult) -> bool:
    if result.passed:
        return False
    return not any(
        issue.code == "container_deployment_not_supported" for issue in result.issues
    )


def _deployment_reflection(
    result: EvaluationResult,
    tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]],
    repair_round: int,
) -> ReflectionResult:
    evidence = _deployment_reflection_evidence(result, tool_results)
    repair_instruction = (
        "Repair the workspace deployment artifacts, then the Orchestrator will rerun "
        "the same platform deployment tool. Do not start local preview/dev servers or "
        "run Docker manually; AgentHub platform tools own deployment.\n"
        f"Deployment repair round: {repair_round + 1}.\n"
        "Focus on the files needed by the failed deployment, such as index.html for "
        "static releases or Dockerfile/application health routes for container deploys.\n"
        f"Deployment evidence:\n- " + "\n- ".join(evidence)
    )
    return ReflectionResult(
        failure_category="deployment_health_failed",
        summary="Deployment health failed after platform deployment.",
        evidence=evidence,
        repair_instruction=repair_instruction,
    )


def _deployment_reflection_evidence(
    result: EvaluationResult,
    tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]],
) -> list[str]:
    evidence = [
        f"{issue.code}: {issue.message}"
        + (f" Repair hint: {issue.repair_hint}" if issue.repair_hint else "")
        for issue in result.issues[:5]
    ]
    for tool_name, arguments, tool_result in tool_results[:5]:
        payload = _json_payload(tool_result.output)
        detail = {
            "tool": tool_name,
            "arguments": arguments,
            "status": payload.get("status"),
            "kind": payload.get("kind"),
            "error": payload.get("error"),
            "logs_preview": payload.get("logs_preview"),
            "logs_tail": payload.get("logs_tail"),
        }
        evidence.append(_truncate(json.dumps(detail, ensure_ascii=False), 1200))
    return evidence[:8]


def _deployment_repair_expected_output(user_request: str, entry_path: str | None) -> str:
    outputs: list[str] = []
    if entry_path:
        outputs.append(entry_path)
    if CONTAINER_INTENT_RE.search(user_request):
        outputs.extend(["Dockerfile", "application files with a working health route"])
    return "\n".join(outputs) or "deployment artifacts"


def _quality_passed_text(
    deployment_result: EvaluationResult | None,
    deployment_repair_rounds: int = 0,
) -> str:
    lines = [
        "Browser quality verification passed.",
        "Evaluation: browser_preview_quality passed.",
    ]
    if deployment_result is not None:
        lines.append(f"Evaluation: deployment_health {deployment_result.status}.")
        if deployment_repair_rounds:
            lines.append(f"Deployment repair rounds: {deployment_repair_rounds}.")
        if deployment_result.issues:
            first_issue = deployment_result.issues[0]
            lines.append(f"Deployment health issue: {first_issue.code} - {first_issue.message}")
    return "\n".join(lines) + "\n"


async def _record_evaluation_started(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    evaluator: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if config.get("orchestrator_evaluation_enabled", True) is False:
        return
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_started",
        agent_id="orchestrator",
        payload={"evaluator": evaluator, **(payload or {})},
    )


async def _record_evaluation_result(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    result: EvaluationResult,
    reflection: ReflectionResult | None = None,
) -> None:
    if config.get("orchestrator_evaluation_enabled", True) is False:
        return
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_result",
        agent_id="orchestrator",
        payload={"results": evaluation_results_payload([result])},
    )
    if reflection is not None:
        await _memory_record_event(
            config,
            run_context,
            event_type="reflection_created",
            agent_id="orchestrator",
            payload={"reflection": reflection_payload(reflection)},
        )
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_finished",
        agent_id="orchestrator",
        payload={"evaluator": result.evaluator, "status": result.status},
    )


async def _record_evaluation_failure(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    evaluator: str,
    code: str,
    message: str,
    *,
    checked_artifacts: list[str] | None = None,
    repair_hint: str | None = None,
) -> None:
    issue = EvaluationIssue(
        code=code,
        message=_truncate(message, 1000),
        evidence=_truncate(message, 1000),
        repair_hint=repair_hint,
    )
    result = EvaluationResult(
        evaluator=evaluator,
        status="failed",
        passed=False,
        severity="major",
        issues=[issue],
        checked_artifacts=checked_artifacts or [],
    )
    reflection = ReflectionResult(
        failure_category="evaluation_failed",
        summary=f"{evaluator} failed.",
        evidence=[f"{code}: {_truncate(message, 500)}"],
        repair_instruction=repair_hint or f"Fix the issues reported by {evaluator}.",
    )
    await _record_evaluation_result(config, run_context, result, reflection)


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
