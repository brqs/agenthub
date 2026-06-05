"""User-facing response presentation for Orchestrator execution."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator.evaluation import evaluation_results_payload
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage

POLISH_SYSTEM_PROMPT = """\
You rewrite AgentHub Orchestrator completion facts into a concise user-facing final answer.
Style: natural Claude/OpenCode coding-agent response. Be accurate, calm, and result-oriented.
Use only the provided facts. Do not invent completed work, files, URLs, or validation results.
Mention failures or manual review needs clearly.
Never reveal internal orchestration/debug terms, task ids, call ids, raw tool output,
JSON, code blocks, agent @ ids, hidden reasoning, ReAct traces, or planner labels.
"""

FORBIDDEN_VISIBLE_PATTERNS = (
    "ReAct step",
    "Observation:",
    "Action:",
    "Tools:",
    "result ok",
    "call_",
    "Execution summary",
    "LLM planner",
    "legacy template",
    "Previous conversation context",
    "Current user request",
    "You are Agent:",
    "You are observing a group conversation",
    "Do not run, suggest, or output shell commands",
    "Messages prefixed with [Agent:",
)
MAX_PRESENTED_ITEMS = 8
MAX_FACT_TEXT_CHARS = 6000


@dataclass(frozen=True, slots=True)
class ToolResultFact:
    tool_name: str
    status: str
    output: str
    arguments: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ResponseFacts:
    user_request: str
    overall_status: str
    completed: list[str]
    needs_attention: list[str]
    artifacts: list[str]
    changed_files: list[str]
    verification: list[str]
    review: list[str]
    urls: list[str]
    raw_summary_excerpt: str


async def presented_response_text(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    tasks: Sequence[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext,
    raw_summary: str,
    *,
    tool_results: Sequence[ToolResultFact] = (),
) -> str:
    """Return the final user-visible answer while preserving raw summary elsewhere."""

    facts = _response_facts(
        messages,
        tasks,
        task_states,
        run_context,
        raw_summary,
        tool_results,
    )
    fallback = deterministic_response_text(facts)
    if not _polish_enabled(config):
        return fallback
    polished = await _polished_response_text(config, facts)
    if not polished or _contains_forbidden_visible_text(polished):
        return fallback
    return _ensure_trailing_newline(polished.strip())


def deterministic_response_text(facts: ResponseFacts) -> str:
    if _raw_summary_is_safe_final_text(facts):
        return _ensure_trailing_newline(facts.raw_summary_excerpt)
    zh = _prefers_chinese(facts.user_request)
    lines: list[str] = []
    if zh:
        lines.append(_zh_status_line(facts.overall_status))
        if facts.completed:
            lines.extend(["", "完成内容：", *[f"- {item}" for item in facts.completed]])
        if facts.artifacts or facts.changed_files:
            lines.extend(
                [
                    "",
                    "文件和产物：",
                    *[f"- {item}" for item in _dedupe([*facts.artifacts, *facts.changed_files])],
                ]
            )
        if facts.urls:
            lines.extend(["", "链接：", *[f"- {item}" for item in facts.urls]])
        if facts.verification:
            lines.extend(["", "验证结果：", *[f"- {item}" for item in facts.verification]])
        if facts.review:
            lines.extend(["", "Review：", *[f"- {item}" for item in facts.review]])
        if facts.needs_attention:
            lines.extend(
                ["", "需要注意：", *[f"- {item}" for item in facts.needs_attention]]
            )
        return _ensure_trailing_newline("\n".join(lines))

    lines.append(_en_status_line(facts.overall_status))
    if facts.completed:
        lines.extend(["", "Completed:", *[f"- {item}" for item in facts.completed]])
    if facts.artifacts or facts.changed_files:
        lines.extend(
            [
                "",
                "Files and artifacts:",
                *[f"- {item}" for item in _dedupe([*facts.artifacts, *facts.changed_files])],
            ]
        )
    if facts.urls:
        lines.extend(["", "Links:", *[f"- {item}" for item in facts.urls]])
    if facts.verification:
        lines.extend(["", "Validation:", *[f"- {item}" for item in facts.verification]])
    if facts.review:
        lines.extend(["", "Review:", *[f"- {item}" for item in facts.review]])
    if facts.needs_attention:
        lines.extend(["", "Needs attention:", *[f"- {item}" for item in facts.needs_attention]])
    return _ensure_trailing_newline("\n".join(lines))


def _response_facts(
    messages: list[ChatMessage],
    tasks: Sequence[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext,
    raw_summary: str,
    tool_results: Sequence[ToolResultFact],
) -> ResponseFacts:
    user_request = _latest_user_request(messages)
    task_items = list(tasks)
    states = _effective_states(task_items, task_states, run_context)
    completed: list[str] = []
    needs_attention: list[str] = []
    artifacts: list[str] = []
    changed_files: list[str] = []
    verification: list[str] = []
    review: list[str] = []

    for task in task_items:
        state = states.get(task.task_id, TaskState.PENDING)
        result = run_context.results.get(task.task_id)
        title = _clean_title(task.title)
        if state == TaskState.SUCCEEDED:
            completed.append(title)
        elif state == TaskState.SKIPPED:
            needs_attention.append(f"{title}: skipped because an earlier step did not complete")
        elif state == TaskState.ARTIFACT_MISSING:
            needs_attention.append(f"{title}: expected file output was not found")
        elif state == TaskState.EVALUATION_FAILED:
            needs_attention.append(f"{title}: validation did not pass")
        elif state == TaskState.FAILED:
            needs_attention.append(f"{title}: did not complete successfully")
        elif state == TaskState.PENDING:
            needs_attention.append(f"{title}: was not run before orchestration stopped")
        _collect_result_facts(
            result,
            artifacts=artifacts,
            changed_files=changed_files,
            verification=verification,
            review=review,
            needs_attention=needs_attention,
        )

    if not task_items and run_context.result_order:
        for task_id in run_context.result_order:
            result = run_context.results[task_id]
            if result.final_state == TaskState.SUCCEEDED:
                completed.append(_clean_title(result.title))
            elif result.final_state == TaskState.PENDING:
                needs_attention.append(
                    f"{_clean_title(result.title)}: was not run before orchestration stopped"
                )
            else:
                needs_attention.append(
                    f"{_clean_title(result.title)}: {result.final_state.value.replace('_', ' ')}"
                )
            _collect_result_facts(
                result,
                artifacts=artifacts,
                changed_files=changed_files,
                verification=verification,
                review=review,
                needs_attention=needs_attention,
            )

    urls = _tool_urls(tool_results)
    needs_attention.extend(_tool_attention(tool_results))
    overall_status = _overall_status(states.values(), run_context, needs_attention)
    return ResponseFacts(
        user_request=user_request,
        overall_status=overall_status,
        completed=_dedupe(completed)[:MAX_PRESENTED_ITEMS],
        needs_attention=_dedupe(needs_attention)[:MAX_PRESENTED_ITEMS],
        artifacts=_dedupe(artifacts)[:MAX_PRESENTED_ITEMS],
        changed_files=_dedupe(changed_files)[:MAX_PRESENTED_ITEMS],
        verification=_dedupe(verification)[:MAX_PRESENTED_ITEMS],
        review=_dedupe(review)[:MAX_PRESENTED_ITEMS],
        urls=_dedupe(urls)[:MAX_PRESENTED_ITEMS],
        raw_summary_excerpt=_truncate_for_facts(raw_summary, 1200),
    )


def _collect_result_facts(
    result: TaskResult | None,
    *,
    artifacts: list[str],
    changed_files: list[str],
    verification: list[str],
    review: list[str],
    needs_attention: list[str],
) -> None:
    if result is None or not result.attempts:
        return
    for conflict in result.workspace_conflicts:
        path = conflict.get("path") if isinstance(conflict, Mapping) else None
        if isinstance(path, str) and path:
            needs_attention.append(f"{path}: concurrent workspace edits may need review")
    had_failed_evaluation = False
    for attempt in result.attempts:
        artifacts.extend(attempt.artifact_paths)
        changed_files.extend(attempt.file_changes.get("created", []))
        changed_files.extend(attempt.file_changes.get("modified", []))
        if attempt.review_outcome:
            review.append(_review_line(attempt.review_outcome))
        eval_payloads = evaluation_results_payload(attempt.evaluation_results)
        if any(payload.get("status") == "failed" for payload in eval_payloads):
            had_failed_evaluation = True
        verification.extend(_evaluation_lines(eval_payloads))
    final_attempt = result.attempts[-1]
    if had_failed_evaluation and result.final_state == TaskState.SUCCEEDED:
        verification.append("An earlier validation failed; the repair passed afterward.")
    if len(result.attempts) > 1 and result.final_state == TaskState.SUCCEEDED:
        verification.append("A retry/repair completed successfully.")
    if final_attempt.review_outcome and final_attempt.review_outcome != "passed":
        review.append("Review feedback was captured for follow-up or repair.")


def _evaluation_lines(payloads: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    passed = sum(
        1
        for payload in payloads
        if payload.get("passed") is True and payload.get("status") != "skipped"
    )
    failed = sum(1 for payload in payloads if payload.get("status") == "failed")
    if passed and not failed:
        lines.append(f"{passed} validation check(s) passed.")
    elif passed or failed:
        lines.append(f"{passed} validation check(s) passed; {failed} need attention.")
    for payload in payloads:
        evaluator = payload.get("evaluator")
        if evaluator == "workflow_dry_run":
            checked = payload.get("checked_artifacts")
            path = checked[0] if isinstance(checked, list) and checked else "workflow"
            status = payload.get("dry_run_status") or payload.get("status") or "unknown"
            lines.append(f"Workflow dry-run for {path} {status}.")
        if evaluator == "manual_review_required":
            checked = payload.get("checked_artifacts")
            artifacts = (
                ", ".join(str(item) for item in checked)
                if isinstance(checked, list)
                else ""
            )
            lines.append(f"Manual review is still required for {artifacts or 'an artifact'}.")
    return lines


def _review_line(outcome: str) -> str:
    normalized = outcome.strip().lower()
    if normalized == "passed":
        return "Review passed."
    if normalized in {"needs_repair", "repair_requested", "failed"}:
        return "Review found changes to address."
    return f"Review outcome: {outcome}."


def _tool_urls(tool_results: Sequence[ToolResultFact]) -> list[str]:
    urls: list[str] = []
    for item in tool_results:
        payload = _json_object(item.output)
        for key in ("url", "preview_url", "deployment_url", "healthcheck_url", "download_url"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                urls.append(value)
        card = payload.get("status_card")
        if isinstance(card, Mapping):
            for key in ("url", "healthcheck_url", "download_url"):
                value = card.get(key)
                if isinstance(value, str) and value:
                    urls.append(value)
    return urls


def _tool_attention(tool_results: Sequence[ToolResultFact]) -> list[str]:
    attention: list[str] = []
    for item in tool_results:
        payload = _json_object(item.output)
        status = str(payload.get("status") or item.status)
        if item.status == "ok" and status not in {"error", "failed"}:
            continue
        label = _friendly_tool_label(item.tool_name)
        error = payload.get("error") or payload.get("message") or item.status
        attention.append(f"{label}: {str(error)[:180]}")
    return attention


async def _polished_response_text(
    config: Mapping[str, Any],
    facts: ResponseFacts,
) -> str | None:
    gateway = _polish_gateway(config)
    if gateway is None:
        return None
    try:
        async with asyncio.timeout(_polish_timeout(config)):
            parts: list[str] = []
            async for chunk in gateway.stream(
                [
                    ChatMessage(
                        role="user",
                        content=_facts_prompt(facts),
                    )
                ],
                system_prompt=POLISH_SYSTEM_PROMPT,
                config=_polish_model_config(config),
            ):
                if chunk.event_type == "error":
                    return None
                if chunk.text_delta:
                    parts.append(chunk.text_delta)
            text = "".join(parts).strip()
    except Exception:  # noqa: BLE001
        return None
    return text or None


def _facts_prompt(facts: ResponseFacts) -> str:
    payload = {
        "user_request": _truncate_for_facts(facts.user_request, 800),
        "overall_status": facts.overall_status,
        "completed": facts.completed,
        "needs_attention": facts.needs_attention,
        "artifacts": facts.artifacts,
        "changed_files": facts.changed_files,
        "verification": facts.verification,
        "review": facts.review,
        "urls": facts.urls,
        "output_requirements": [
            "short natural final answer",
            "no internal terms or ids",
            "no code blocks",
            "do not mention unavailable facts",
        ],
    }
    return _truncate_for_facts(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        MAX_FACT_TEXT_CHARS,
    )


def _polish_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_response_polish_enabled") is True


def _polish_gateway(config: Mapping[str, Any]) -> Any | None:
    gateway = config.get("orchestrator_response_polish_gateway")
    if gateway is not None:
        return gateway
    backend = (
        config.get("orchestrator_response_polish_model_backend")
        or config.get("answer_model_backend")
        or config.get("planner_model_backend")
        or config.get("model_backend")
    )
    if not isinstance(backend, str) or not backend.strip():
        return None
    return ModelGateway(
        backend,
        default_config=_polish_model_config(config),
        agent_id="orchestrator-response-polish",
        system_prompt=POLISH_SYSTEM_PROMPT,
    )


def _polish_model_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw = config.get("orchestrator_response_polish_config")
    if raw is None:
        raw = config.get("orchestrator_answer_config")
    model_config: dict[str, Any] = {"temperature": 0.2}
    if isinstance(raw, Mapping):
        model_config.update(dict(raw))
    model_config["max_tokens"] = _positive_int(
        config.get("orchestrator_response_polish_max_tokens"),
        900,
    )
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in model_config:
            model_config[key] = config[key]
    model_config.setdefault("request_timeout_seconds", _polish_timeout(config))
    return model_config


def _polish_timeout(config: Mapping[str, Any]) -> float:
    raw = config.get("orchestrator_response_polish_timeout_seconds")
    if isinstance(raw, bool):
        return 12.0
    if isinstance(raw, (int, float)) and raw > 0:
        return min(float(raw), 30.0)
    return 12.0


def _effective_states(
    tasks: Sequence[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext,
) -> dict[str, TaskState]:
    states = dict(task_states)
    for task in tasks:
        if task.task_id in states:
            continue
        result = run_context.results.get(task.task_id)
        if result is not None:
            states[task.task_id] = result.final_state
    return states


def _overall_status(
    states: Iterable[TaskState],
    run_context: OrchestratorRunContext,
    needs_attention: Sequence[str],
) -> str:
    terminal_states = list(states) or [
        result.final_state for result in run_context.results.values()
    ]
    failed_states = {
        TaskState.FAILED,
        TaskState.ARTIFACT_MISSING,
        TaskState.EVALUATION_FAILED,
    }
    has_completed = any(state == TaskState.SUCCEEDED for state in terminal_states)
    has_pending = any(state == TaskState.PENDING for state in terminal_states)
    if has_pending:
        return "partial" if has_completed else "failed"
    if any(state in failed_states for state in terminal_states) or needs_attention:
        if has_completed:
            return "partial"
        return "failed"
    return "done"


def _en_status_line(status: str) -> str:
    if status == "partial":
        return (
            "I completed the parts that could be finished, with a few items still "
            "needing attention."
        )
    if status == "failed":
        return "I could not complete the request successfully yet."
    return "Done. I completed the requested work."


def _zh_status_line(status: str) -> str:
    if status == "partial":
        return "已完成可完成的部分，但还有几项需要注意。"
    if status == "failed":
        return "这次还没有成功完成请求。"
    return "已完成。本次请求已经处理完毕。"


def _latest_user_request(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _prefers_chinese(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _contains_forbidden_visible_text(text: str) -> bool:
    lowered = text.lower()
    for pattern in FORBIDDEN_VISIBLE_PATTERNS:
        if pattern.lower() in lowered:
            return True
    return bool(re.search(r"\borch\.[\w.-]+", text))


def _raw_summary_is_safe_final_text(facts: ResponseFacts) -> bool:
    if any(
        [
            facts.completed,
            facts.needs_attention,
            facts.artifacts,
            facts.changed_files,
            facts.verification,
            facts.review,
            facts.urls,
        ]
    ):
        return False
    text = facts.raw_summary_excerpt.strip()
    if not text or len(text) > 1200:
        return False
    return not _contains_forbidden_visible_text(text)


def _json_object(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _friendly_tool_label(tool_name: str) -> str:
    labels = {
        "start_workspace_preview": "Preview",
        "verify_web_preview": "Browser verification",
        "create_deployment": "Deployment",
        "package_workspace_source": "Source package",
        "get_deployment_status": "Deployment status",
    }
    return labels.get(tool_name, "Platform operation")


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip() or "Work item"


def _dedupe(values: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _truncate_for_facts(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 15].rstrip() + "...[truncated]"


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return default
    return value


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"
