"""Deployment/release tool handling for orchestrator quality gates."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.agents.orchestrator._internal.presentation_markers import (
    artifact_evidence_presentation,
)
from app.agents.orchestrator._internal.quality.preview import (
    json_payload,
    optional_str,
    tool_call,
    tool_result,
    truncate,
)
from app.agents.orchestrator.evaluation import (
    EvaluationIssue,
    EvaluationResult,
    ReflectionResult,
)
from app.agents.orchestrator.tools import OrchestratorToolResult
from app.agents.types import StreamChunk

RELEASE_INTENT_RE = re.compile(r"(?i)(部署|发布|上线|deploy(?:ed|ment)?)")
SOURCE_EXPORT_INTENT_RE = re.compile(r"(?i)(源码|源代码|打包|下载|source|zip)")
CONTAINER_INTENT_RE = re.compile(r"(?i)(容器|容器化|docker|container)")


async def run_deployment_tools(
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


def deployment_health_result(
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
    pending: list[str] = []
    for tool_name, arguments, result in tool_results:
        kind = str(arguments.get("kind") or tool_name)
        checked.append(kind)
        payload = json_payload(result.output)
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
        if status in {"queued", "publishing"}:
            pending.append(kind)
            continue
        if tool_name == "package_workspace_source":
            if status != "published" or not optional_str(payload.get("download_url")):
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
        if status == "failed":
            failure_category = optional_str(payload.get("failure_category"))
            last_error_code = optional_str(payload.get("last_error_code"))
            repair_hint = _deployment_failure_repair_hint(failure_category)
            issues.append(
                EvaluationIssue(
                    code=failure_category or "deployment_failed",
                    message=f"{kind} deployment failed.",
                    evidence=result.output,
                    repair_hint=(
                        f"{repair_hint} Last error code: {last_error_code}."
                        if last_error_code
                        else repair_hint
                    ),
                )
            )
            continue
        if kind == "container":
            if not optional_str(payload.get("healthcheck_url")):
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
                        repair_hint="Fix container startup and health behavior, then redeploy.",
                    )
                )
        if status != "published" or not optional_str(payload.get("url")):
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
        status="failed" if issues else "skipped" if pending else "passed",
        passed=not issues,
        severity="major" if issues else "info",
        issues=issues,
        checked_artifacts=checked,
    )


def deployment_result_repairable(result: EvaluationResult) -> bool:
    if result.passed:
        return False
    return not any(
        issue.code == "container_deployment_not_supported" for issue in result.issues
    )


def deployment_reflection(
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


def deployment_repair_expected_output(user_request: str, entry_path: str | None) -> str:
    outputs: list[str] = []
    if entry_path:
        outputs.append(entry_path)
    if CONTAINER_INTENT_RE.search(user_request):
        outputs.extend(["Dockerfile", "application files with a working health route"])
    return "\n".join(outputs) or "deployment artifacts"


def quality_passed_text(
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
            lines.append(
                f"Deployment health issue: {first_issue.code} - {first_issue.message}"
            )
    return "\n".join(lines) + "\n"


async def _call_deployment_tool(
    executor: Any,
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    next_block_index: int,
    deployment_tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]]
    | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    yield tool_call(call_id, tool_name, arguments), next_block_index
    result = await executor(tool_name, arguments)
    if deployment_tool_results is not None:
        deployment_tool_results.append((tool_name, dict(arguments), result))
    yield tool_result(call_id, result), next_block_index
    status_card = _deployment_status_card(result.output)
    if status_card is not None:
        yield StreamChunk(
            event_type="block_start",
            block_index=next_block_index,
            block_type="deployment_status",
            metadata={
                **status_card,
                "presentation": artifact_evidence_presentation(),
            },
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


def _deployment_failure_repair_hint(failure_category: str | None) -> str:
    if failure_category == "build_failed":
        return "Fix the Dockerfile, build context, copied files, or dependency install step."
    if failure_category == "run_failed":
        return "Fix the container startup command, exposed port, or runtime dependency failure."
    if failure_category == "health_check_failed":
        return "Fix the app health route, listen address, container_port, or startup readiness."
    if failure_category == "policy_rejected":
        return "Adjust the deployment request or workspace artifact to satisfy platform policy."
    if failure_category == "port_pool_exhausted":
        return (
            "Retry after an existing container deployment is stopped or the port pool "
            "is expanded."
        )
    if failure_category == "runtime_unavailable":
        return "Ask an operator to enable the configured container runtime."
    if failure_category == "cleanup_failed":
        return "Ask an operator to inspect deployment cleanup before retrying."
    if failure_category == "timeout":
        return "Reduce startup/build time or fix a worker timeout before retrying deployment."
    return "Fix the deployment artifact and rerun the platform deployment tool."


def _deployment_reflection_evidence(
    result: EvaluationResult,
    tool_results: list[tuple[str, dict[str, Any], OrchestratorToolResult]],
) -> list[str]:
    evidence = [
        f"{issue.code}: {issue.message}"
        + (f" Repair hint: {issue.repair_hint}" if issue.repair_hint else "")
        for issue in result.issues[:5]
    ]
    for tool_name, arguments, result_item in tool_results[:5]:
        payload = json_payload(result_item.output)
        detail = {
            "tool": tool_name,
            "arguments": arguments,
            "status": payload.get("status"),
            "kind": payload.get("kind"),
            "error": payload.get("error"),
            "logs_preview": payload.get("logs_preview"),
            "logs_tail": payload.get("logs_tail"),
        }
        evidence.append(truncate(json.dumps(detail, ensure_ascii=False), 1200))
    return evidence[:8]
