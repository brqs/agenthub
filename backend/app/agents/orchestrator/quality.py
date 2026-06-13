"""Deterministic preview quality gate for Orchestrator frontend tasks."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.agents.orchestrator._internal.execution.fulfillment import (
    fulfillment_payload as _fulfillment_payload,
)
from app.agents.orchestrator._internal.execution.fulfillment import (
    mark_tool_fulfillment as _mark_tool_fulfillment,
)
from app.agents.orchestrator._internal.memory import record_event as _memory_record_event
from app.agents.orchestrator._internal.presentation_markers import (
    artifact_evidence_presentation as _artifact_evidence_presentation,
)
from app.agents.orchestrator._internal.quality.deployment import (
    CONTAINER_INTENT_RE,
)
from app.agents.orchestrator._internal.quality.deployment import (
    deployment_health_result as _deployment_health_result,
)
from app.agents.orchestrator._internal.quality.deployment import (
    deployment_reflection as _deployment_reflection,
)
from app.agents.orchestrator._internal.quality.deployment import (
    deployment_repair_expected_output as _deployment_repair_expected_output,
)
from app.agents.orchestrator._internal.quality.deployment import (
    deployment_result_repairable as _deployment_result_repairable,
)
from app.agents.orchestrator._internal.quality.deployment import (
    quality_passed_text as _quality_passed_text,
)
from app.agents.orchestrator._internal.quality.deployment import (
    run_deployment_tools as _run_deployment_tools,
)
from app.agents.orchestrator._internal.quality.preview import error as _error
from app.agents.orchestrator._internal.quality.preview import (
    find_preview_entry as _find_preview_entry,
)
from app.agents.orchestrator._internal.quality.preview import json_output as _json_output
from app.agents.orchestrator._internal.quality.preview import json_payload as _json_payload
from app.agents.orchestrator._internal.quality.preview import (
    max_repair_rounds as _max_repair_rounds,
)
from app.agents.orchestrator._internal.quality.preview import optional_str as _optional_str
from app.agents.orchestrator._internal.quality.preview import repair_agent as _repair_agent
from app.agents.orchestrator._internal.quality.preview import (
    repair_instruction as _repair_instruction,
)
from app.agents.orchestrator._internal.quality.preview import required_text as _required_text
from app.agents.orchestrator._internal.quality.preview import tool_call as _tool_call
from app.agents.orchestrator._internal.quality.preview import tool_result as _tool_result
from app.agents.orchestrator._internal.quality.preview import truncate as _truncate
from app.agents.orchestrator.evaluation import (
    EvaluationIssue,
    EvaluationResult,
    ReflectionResult,
    evaluation_results_payload,
    reflection_payload,
)
from app.agents.orchestrator.tools import OrchestratorToolResult
from app.agents.orchestrator.types import OrchestratorRunContext, SubTask
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

DEPLOY_INTENT_RE = re.compile(
    r"(?i)(部署|发布|上线|端口|preview\s+(?:on|at|to)|deploy(?:ed|ment)?|port\s*\d{2,5})"
)
FRONTEND_INTENT_RE = re.compile(
    r"(?i)(前端|网页|页面|网站|站点|html|css|javascript|js|frontend|web|website|site)"
)
BROWSER_VERIFY_INTENT_RE = re.compile(
    r"(?i)(浏览器|质量验收|移动端|按钮|交互|browser|quality|viewport|mobile)"
)
NEGATIVE_PREVIEW_INTENT_RE = re.compile(
    r"(不要|无需|不需要|禁止|避免)\s*(?:调用|执行|使用|进行|触发)?\s*"
    r"(?:预览|部署|发布|上线)|"
    r"(no|without|skip|avoid|do\s+not|don't)\s+(?:preview|deploy|deployment)",
    re.I,
)
DEPLOYMENT_REPAIR_WAIT_INTENT_RE = re.compile(
    r"(?i)(deployment_health|deployment\s+logs|until\s+(?:it\s+)?(?:returns\s+)?published|"
    r"redeploy|重新调用\s*create_deployment|直到返回\s*published|容器健康|部署日志)"
)
REQUESTED_PORT_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")
REPAIR_AGENT_MISSING_TEXT = (
    "浏览器级质量验收暂时无法继续自动修复：当前没有可用的质量修复 Agent。"
    "我已经保留了本轮验收证据；请检查可用 Agent 配置，或先补齐静态前端产物后重试。"
)
ONE_CLICK_CONTAINER_AUTOMATION_KIND = "one_click_container_deploy"

PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]


class TextBlockWithNext(Protocol):
    def __call__(
        self,
        block_index: int,
        text: str,
        *,
        agent_id: str = "orchestrator",
        presentation: Mapping[str, Any] | None = None,
    ) -> Iterable[tuple[StreamChunk, int]]: ...


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


@dataclass
class DeploymentRepairState:
    result: EvaluationResult | None = None
    repair_rounds: int = 0


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
    is_one_click_container = _is_one_click_container_quality_gate(config)
    if not is_one_click_container and not _should_run_quality_gate(user_request):
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

    max_rounds = _max_repair_rounds(config, positive_int_config)
    requested_port = _requested_port(user_request)
    if is_one_click_container:
        state = DeploymentRepairState()
        async for chunk, updated_block_index in _run_deployment_repair_loop(
            config=config,
            executor=executor,
            user_request=user_request,
            entry_path=None,
            requested_port=requested_port or 8000,
            next_block_index=next_block_index,
            run_context=run_context,
            max_rounds=max_rounds,
            messages=messages,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
            run_task=run_task,
            positive_int_config=positive_int_config,
            state=state,
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index
        for chunk, updated_block_index in text_block_with_next(
            next_block_index,
            _quality_passed_text(state.result, state.repair_rounds),
            presentation=_artifact_evidence_presentation(),
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index
        return

    await _record_evaluation_started(
        config,
        run_context,
        "browser_preview_quality",
        {"requested_port": _requested_preview_port(user_request)},
    )
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
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                REPAIR_AGENT_MISSING_TEXT,
                presentation=_artifact_evidence_presentation(),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
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
    requested_preview_port = _requested_preview_port(user_request)
    if requested_preview_port is not None:
        preview_args["requested_port"] = requested_preview_port

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
    await _record_fulfillment_tool_result(
        config,
        run_context,
        preview_call_id,
        "start_workspace_preview",
        result,
    )
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
        presentation=_artifact_evidence_presentation(),
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
                "presentation": _artifact_evidence_presentation(),
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
            await _record_fulfillment_tool_result(
                config,
                run_context,
                refresh_call_id,
                "start_workspace_preview",
                refresh_result,
            )
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
        await _record_fulfillment_tool_result(
            config,
            run_context,
            verify_call_id,
            "verify_web_preview",
            verify_result,
        )
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
            state = DeploymentRepairState()
            async for chunk, updated_block_index in _run_deployment_repair_loop(
                config=config,
                executor=executor,
                user_request=user_request,
                entry_path=entry_path,
                requested_port=requested_port,
                next_block_index=next_block_index,
                run_context=run_context,
                max_rounds=max_rounds,
                messages=messages,
                workspace_path=workspace_path,
                tool_specs=tool_specs,
                run_task=run_task,
                positive_int_config=positive_int_config,
                state=state,
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                _quality_passed_text(state.result, state.repair_rounds),
                presentation=_artifact_evidence_presentation(),
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
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                REPAIR_AGENT_MISSING_TEXT,
                presentation=_artifact_evidence_presentation(),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
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


async def _run_deployment_repair_loop(
    *,
    config: Mapping[str, Any],
    executor: Any,
    user_request: str,
    entry_path: str | None,
    requested_port: int | None,
    next_block_index: int,
    run_context: OrchestratorRunContext,
    max_rounds: int,
    messages: list[ChatMessage],
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    run_task: RunTaskWithPrefix,
    positive_int_config: PositiveIntConfig,
    state: DeploymentRepairState,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    deployment_result: EvaluationResult | None = None
    deployment_repair_round = 0
    while True:
        deployment_tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]] = []
        call_id_suffix = (
            "" if deployment_repair_round == 0 else f".retry.{deployment_repair_round}"
        )
        wait_for_container_terminal = _should_wait_for_container_terminal(
            config,
            user_request,
        )
        async for chunk, updated_block_index in _run_deployment_tools(
            executor=executor,
            user_request=user_request,
            entry_path=entry_path,
            requested_port=requested_port,
            next_block_index=next_block_index,
            wait_for_container_terminal=wait_for_container_terminal,
            container_wait_timeout_seconds=_container_wait_timeout_seconds(
                config,
                positive_int_config,
                user_request,
            ),
            deployment_tool_results=deployment_tool_results,
            call_id_suffix=call_id_suffix,
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index
            if chunk.event_type == "tool_result" and chunk.tool_name:
                await _record_fulfillment_tool_result(
                    config,
                    run_context,
                    chunk.call_id,
                    chunk.tool_name,
                    OrchestratorToolResult(
                        status=chunk.tool_status or "error",
                        output=chunk.tool_output or "",
                        error_code=chunk.error_code,
                    ),
                )
        deployment_result = _deployment_health_result(
            user_request,
            deployment_tool_results,
        )
        for tool_name, _arguments, tool_result in deployment_tool_results:
            await _record_fulfillment_tool_result(
                config,
                run_context,
                None,
                tool_name,
                tool_result,
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
    state.result = deployment_result
    state.repair_rounds = deployment_repair_round


def _is_one_click_container_quality_gate(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_automation_kind") == ONE_CLICK_CONTAINER_AUTOMATION_KIND


def _should_run_quality_gate(user_request: str) -> bool:
    if not user_request:
        return False
    if NEGATIVE_PREVIEW_INTENT_RE.search(user_request):
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


def _requested_preview_port(text: str) -> int | None:
    port = _requested_port(text)
    if port is None:
        return None
    if port == 8000 and CONTAINER_INTENT_RE.search(text):
        return None
    return port


def _container_wait_timeout_seconds(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
    user_request: str = "",
) -> int | None:
    if not _should_wait_for_container_terminal(config, user_request):
        return None
    return positive_int_config(
        config,
        "orchestrator_container_deployment_wait_timeout_seconds",
        180,
    )


def _should_wait_for_container_terminal(
    config: Mapping[str, Any],
    user_request: str,
) -> bool:
    if config.get("orchestrator_container_deployment_wait_for_terminal") is True:
        return True
    return bool(DEPLOYMENT_REPAIR_WAIT_INTENT_RE.search(user_request or ""))


async def _record_fulfillment_tool_result(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    call_id: str | None,
    tool_name: str,
    result: OrchestratorToolResult,
) -> None:
    _mark_tool_fulfillment(run_context, tool_name, result.status, result.output)
    await _memory_record_event(
        config,
        run_context,
        event_type="command_fulfillment_status",
        agent_id="orchestrator",
        payload={
            "stage": "tool_result",
            "call_id": call_id,
            "tool_name": tool_name,
            "tool_status": result.status,
            **_fulfillment_payload(run_context),
        },
    )


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
