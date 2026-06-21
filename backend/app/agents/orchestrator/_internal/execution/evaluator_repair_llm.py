"""LLM suggestion helper for evaluator/browser repair routing."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.agents.orchestrator._internal.execution.attempts import (
    agent_permitted_for_attempt as _agent_permitted_for_attempt,
)
from app.agents.orchestrator._internal.execution.attempts import (
    dedupe_strings as _dedupe_strings,
)
from app.agents.orchestrator._internal.execution.attempts import (
    positive_int_config as _positive_int_config,
)
from app.agents.orchestrator._internal.llm_control import record_llm_control_point
from app.agents.orchestrator._internal.planning.routing import (
    latest_user_request as _latest_user_request,
)
from app.agents.orchestrator._internal.react.decision import (
    _react_config,
    _react_gateway,
)
from app.agents.orchestrator.availability import runtime_cooldown_status
from app.agents.orchestrator.evaluation import (
    evaluation_results_payload as _evaluation_results_payload,
)
from app.agents.orchestrator.evaluation import (
    reflection_payload as _reflection_payload,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage

EVALUATOR_REPAIR_DECISION_ACTIONS = frozenset(
    {"retry_current", "fallback", "finish_with_failure"}
)
SUPPORTED_EVALUATOR_REPAIR_SOURCES = frozenset(
    {"document_quality", "code_static_quality", "browser_preview_quality"}
)
EVALUATOR_REPAIR_DECISION_SYSTEM_PROMPT = (
    "You are AgentHub's Orchestrator evaluator repair advisor. Return strict JSON "
    "only. Do not include markdown. Do not include thought, chain_of_thought, "
    "hidden reasoning, private analysis, prompt text, tokens, stderr, env, or "
    "secrets. Choose action only from retry_current, fallback, "
    "finish_with_failure. You may only reference agent ids from the provided "
    "allowed_agent_ids list."
)


@dataclass(frozen=True, slots=True)
class EvaluatorRepairLlmDecision:
    failure_source: str
    attempt_index: int
    failed_agent_id: str
    failed_state: str
    failed_evaluators: tuple[str, ...]
    checked_artifacts: tuple[str, ...]
    repair_round: int
    allowed_agent_ids: tuple[str, ...]
    model_suggestion: dict[str, Any] | None
    preferred_agent_id: str | None
    allow_revisit: bool
    stop: bool
    status: str
    decision_outcome: str
    reason: str


@dataclass(frozen=True, slots=True)
class _ParsedSuggestion:
    action: str
    agent_id: str | None
    reason: str
    summary: str


def evaluator_optimizer_repair_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_evaluator_optimizer_repair_enabled") is True


async def maybe_task_evaluator_repair_llm_decision(
    config: Mapping[str, Any],
    *,
    task: SubTask,
    messages: Sequence[ChatMessage],
    task_result: TaskResult,
    fallback_agents: list[str],
    max_attempts: int,
    run_context: OrchestratorRunContext,
    excluded_agent_ids: set[str],
) -> EvaluatorRepairLlmDecision | None:
    if not evaluator_optimizer_repair_enabled(config):
        return None
    if task_result.final_state != TaskState.EVALUATION_FAILED:
        return None
    if not task_result.attempts or len(task_result.attempts) >= max_attempts:
        return None

    failed_attempt = task_result.attempts[-1]
    failure_source = _failure_source_from_results(failed_attempt.evaluation_results)
    if failure_source not in {"document_quality", "code_static_quality"}:
        return None

    allowed_agent_ids = tuple(_dedupe_strings([task.agent_id, *fallback_agents]))
    failed_evaluators = tuple(_failed_evaluators(failed_attempt.evaluation_results))
    checked_artifacts = tuple(_checked_artifacts(failed_attempt.evaluation_results))
    repair_round = max(0, len(task_result.attempts) - 1)
    max_repair_rounds = max(0, max_attempts - 1)
    prompt_payload = _task_prompt_payload(
        config=config,
        messages=messages,
        task=task,
        task_result=task_result,
        failed_attempt=failed_attempt,
        failure_source=failure_source,
        allowed_agent_ids=allowed_agent_ids,
        repair_round=repair_round,
        max_repair_rounds=max_repair_rounds,
        run_context=run_context,
        excluded_agent_ids=excluded_agent_ids,
    )
    return await _maybe_evaluator_repair_llm_decision(
        config,
        prompt_payload=prompt_payload,
        failure_source=failure_source,
        attempt_index=failed_attempt.attempt_index,
        failed_agent_id=failed_attempt.agent_id,
        failed_state=task_result.final_state.value,
        failed_evaluators=failed_evaluators,
        checked_artifacts=checked_artifacts,
        repair_round=repair_round,
        max_repair_rounds=max_repair_rounds,
        allowed_agent_ids=allowed_agent_ids,
        run_context=run_context,
        excluded_agent_ids=excluded_agent_ids,
        current_agent_id=failed_attempt.agent_id,
    )


async def maybe_browser_evaluator_repair_llm_decision(
    config: Mapping[str, Any],
    *,
    messages: Sequence[ChatMessage],
    run_context: OrchestratorRunContext,
    failed_agent_id: str,
    attempt_index: int,
    checked_artifacts: Sequence[str],
    issues: Sequence[Mapping[str, Any]],
    reflection_summary: str,
    repair_instruction: str,
    repair_round: int,
    max_repair_rounds: int,
    allowed_agent_ids: Sequence[str],
) -> EvaluatorRepairLlmDecision | None:
    if not evaluator_optimizer_repair_enabled(config):
        return None

    scoped_allowed_agent_ids = tuple(_dedupe_strings(list(allowed_agent_ids)))
    prompt_payload = _browser_prompt_payload(
        config=config,
        messages=messages,
        run_context=run_context,
        failed_agent_id=failed_agent_id,
        attempt_index=attempt_index,
        checked_artifacts=checked_artifacts,
        issues=issues,
        reflection_summary=reflection_summary,
        repair_instruction=repair_instruction,
        repair_round=repair_round,
        max_repair_rounds=max_repair_rounds,
        allowed_agent_ids=scoped_allowed_agent_ids,
    )
    return await _maybe_evaluator_repair_llm_decision(
        config,
        prompt_payload=prompt_payload,
        failure_source="browser_preview_quality",
        attempt_index=attempt_index,
        failed_agent_id=failed_agent_id,
        failed_state=TaskState.EVALUATION_FAILED.value,
        failed_evaluators=("browser_preview_quality",),
        checked_artifacts=tuple(_dedupe_strings(checked_artifacts)),
        repair_round=repair_round,
        max_repair_rounds=max_repair_rounds,
        allowed_agent_ids=scoped_allowed_agent_ids,
        run_context=run_context,
        excluded_agent_ids=set(),
        current_agent_id=failed_agent_id,
    )


async def record_task_evaluator_repair_llm_decision(
    config: Mapping[str, Any],
    *,
    run_context: OrchestratorRunContext,
    task_id: str | None,
    decision: EvaluatorRepairLlmDecision,
    backend_action: str,
    backend_agent_id: str | None,
    record_event: Any,
) -> None:
    await record_event(
        config,
        run_context,
        event_type="task_evaluator_repair_decision",
        task_id=task_id,
        agent_id="orchestrator",
        payload={
            "failure_source": decision.failure_source,
            "attempt_index": decision.attempt_index,
            "failed_agent_id": decision.failed_agent_id,
            "failed_state": decision.failed_state,
            "failed_evaluators": list(decision.failed_evaluators),
            "checked_artifacts": list(decision.checked_artifacts),
            "repair_round": decision.repair_round,
            "allowed_agent_ids": list(decision.allowed_agent_ids),
            "model_suggestion": decision.model_suggestion,
            "backend_action": backend_action,
            "backend_agent_id": backend_agent_id,
            "decision_outcome": decision.decision_outcome,
            "reason": decision.reason,
        },
    )
    await record_llm_control_point(
        config,
        run_context,
        phase="react_replanner",
        status=decision.status,
        used_llm=True,
        fallback_reason=decision.reason if decision.status != "succeeded" else None,
        decision_summary=_decision_summary(
            decision,
            backend_action=backend_action,
            backend_agent_id=backend_agent_id,
        ),
    )


async def _maybe_evaluator_repair_llm_decision(
    config: Mapping[str, Any],
    *,
    prompt_payload: dict[str, Any],
    failure_source: str,
    attempt_index: int,
    failed_agent_id: str,
    failed_state: str,
    failed_evaluators: tuple[str, ...],
    checked_artifacts: tuple[str, ...],
    repair_round: int,
    max_repair_rounds: int,
    allowed_agent_ids: tuple[str, ...],
    run_context: OrchestratorRunContext,
    excluded_agent_ids: set[str],
    current_agent_id: str,
) -> EvaluatorRepairLlmDecision:
    try:
        suggestion_payload = await _evaluator_repair_decision_payload(
            config,
            prompt_payload=prompt_payload,
        )
        suggestion = _parse_evaluator_repair_suggestion(suggestion_payload)
    except Exception as exc:  # noqa: BLE001
        return EvaluatorRepairLlmDecision(
            failure_source=failure_source,
            attempt_index=attempt_index,
            failed_agent_id=failed_agent_id,
            failed_state=failed_state,
            failed_evaluators=failed_evaluators,
            checked_artifacts=checked_artifacts,
            repair_round=repair_round,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=None,
            preferred_agent_id=None,
            allow_revisit=False,
            stop=False,
            status="fallback",
            decision_outcome="deterministic_fallback",
            reason=_model_failure_reason(exc),
        )

    raw_model_suggestion = _model_suggestion_payload(suggestion)
    if suggestion.action == "finish_with_failure":
        if _finish_with_failure_allowed(
            repair_round=repair_round,
            max_repair_rounds=max_repair_rounds,
        ):
            return EvaluatorRepairLlmDecision(
                failure_source=failure_source,
                attempt_index=attempt_index,
                failed_agent_id=failed_agent_id,
                failed_state=failed_state,
                failed_evaluators=failed_evaluators,
                checked_artifacts=checked_artifacts,
                repair_round=repair_round,
                allowed_agent_ids=allowed_agent_ids,
                model_suggestion=raw_model_suggestion,
                preferred_agent_id=None,
                allow_revisit=False,
                stop=True,
                status="succeeded",
                decision_outcome="accepted",
                reason=_safe_text(suggestion.reason, 240) or "finish_with_failure",
            )
        return _rejected_evaluator_repair_decision(
            failure_source=failure_source,
            attempt_index=attempt_index,
            failed_agent_id=failed_agent_id,
            failed_state=failed_state,
            failed_evaluators=failed_evaluators,
            checked_artifacts=checked_artifacts,
            repair_round=repair_round,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=raw_model_suggestion,
            reason="finish_with_failure_not_allowed",
        )

    if suggestion.action == "retry_current":
        if _retry_current_allowed(
            config,
            run_context,
            current_agent_id,
            excluded_agent_ids=excluded_agent_ids,
        ):
            return EvaluatorRepairLlmDecision(
                failure_source=failure_source,
                attempt_index=attempt_index,
                failed_agent_id=failed_agent_id,
                failed_state=failed_state,
                failed_evaluators=failed_evaluators,
                checked_artifacts=checked_artifacts,
                repair_round=repair_round,
                allowed_agent_ids=allowed_agent_ids,
                model_suggestion=raw_model_suggestion,
                preferred_agent_id=current_agent_id,
                allow_revisit=True,
                stop=False,
                status="succeeded",
                decision_outcome="accepted",
                reason=_safe_text(suggestion.reason, 240) or "retry_current",
            )
        return _rejected_evaluator_repair_decision(
            failure_source=failure_source,
            attempt_index=attempt_index,
            failed_agent_id=failed_agent_id,
            failed_state=failed_state,
            failed_evaluators=failed_evaluators,
            checked_artifacts=checked_artifacts,
            repair_round=repair_round,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=raw_model_suggestion,
            reason="retry_current_not_available",
        )

    remapped = _accepted_fallback_candidate(
        config,
        run_context,
        suggestion.agent_id,
        allowed_agent_ids=allowed_agent_ids,
        excluded_agent_ids=excluded_agent_ids,
        current_agent_id=current_agent_id,
    )
    if remapped is not None:
        preferred_agent_id, allow_revisit, outcome = remapped
        return EvaluatorRepairLlmDecision(
            failure_source=failure_source,
            attempt_index=attempt_index,
            failed_agent_id=failed_agent_id,
            failed_state=failed_state,
            failed_evaluators=failed_evaluators,
            checked_artifacts=checked_artifacts,
            repair_round=repair_round,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=raw_model_suggestion,
            preferred_agent_id=preferred_agent_id,
            allow_revisit=allow_revisit,
            stop=False,
            status="succeeded",
            decision_outcome=outcome,
            reason=_safe_text(suggestion.reason, 240) or "fallback",
        )
    return _rejected_evaluator_repair_decision(
        failure_source=failure_source,
        attempt_index=attempt_index,
        failed_agent_id=failed_agent_id,
        failed_state=failed_state,
        failed_evaluators=failed_evaluators,
        checked_artifacts=checked_artifacts,
        repair_round=repair_round,
        allowed_agent_ids=allowed_agent_ids,
        model_suggestion=raw_model_suggestion,
        reason="suggested_agent_not_allowed",
    )


async def _evaluator_repair_decision_payload(
    config: Mapping[str, Any],
    *,
    prompt_payload: dict[str, Any],
) -> dict[str, Any]:
    gateway = _react_gateway(
        config,
        _positive_int_config,
        EVALUATOR_REPAIR_DECISION_SYSTEM_PROMPT,
    )
    parts: list[str] = []
    async for chunk in gateway.stream(
        [
            ChatMessage(
                role="user",
                content=json.dumps(prompt_payload, ensure_ascii=False),
            )
        ],
        system_prompt=EVALUATOR_REPAIR_DECISION_SYSTEM_PROMPT,
        config=_react_config(config, _positive_int_config),
    ):
        if chunk.event_type == "delta":
            parts.append(chunk.text_delta or chunk.code_delta or "")
        elif chunk.event_type == "error":
            raise ValueError(chunk.error_code or chunk.error or "evaluator_repair_llm_error")
    text = "".join(parts).strip()
    if not text:
        raise ValueError("empty_evaluator_repair_llm_decision")
    payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise ValueError("evaluator_repair_llm_decision_must_be_object")
    return dict(payload)


def _task_prompt_payload(
    *,
    config: Mapping[str, Any],
    messages: Sequence[ChatMessage],
    task: SubTask,
    task_result: TaskResult,
    failed_attempt: TaskAttempt,
    failure_source: str,
    allowed_agent_ids: tuple[str, ...],
    repair_round: int,
    max_repair_rounds: int,
    run_context: OrchestratorRunContext,
    excluded_agent_ids: set[str],
) -> dict[str, Any]:
    return {
        "user_request": _latest_user_request(list(messages)),
        "task": {
            "task_id": task.task_id,
            "title": task.title,
            "instruction": task.instruction,
            "task_type": task.task_type,
            "expected_output": task.expected_output,
        },
        "failure_source": failure_source,
        "attempt_index": failed_attempt.attempt_index,
        "failed_agent_id": failed_attempt.agent_id,
        "failed_state": task_result.final_state.value,
        "failed_reason": _safe_failed_reason(failed_attempt.error or ""),
        "failed_evaluators": _failed_evaluators(failed_attempt.evaluation_results),
        "checked_artifacts": _checked_artifacts(failed_attempt.evaluation_results),
        "issues": _failed_issues(failed_attempt.evaluation_results),
        "reflection_summary": _reflection_summary(failed_attempt.reflection),
        "repair_instruction": _repair_instruction(failed_attempt.reflection),
        "repair_round": repair_round,
        "max_repair_rounds": max_repair_rounds,
        "allowed_agent_ids": list(allowed_agent_ids),
        "agent_candidates": _agent_candidates(
            config,
            run_context,
            allowed_agent_ids=allowed_agent_ids,
            excluded_agent_ids=excluded_agent_ids,
        ),
        "required_output": {
            "action": "retry_current|fallback|finish_with_failure",
            "agent_id": "string|null",
            "reason": "short public reason",
            "summary": "optional short public summary",
        },
    }


def _browser_prompt_payload(
    *,
    config: Mapping[str, Any],
    messages: Sequence[ChatMessage],
    run_context: OrchestratorRunContext,
    failed_agent_id: str,
    attempt_index: int,
    checked_artifacts: Sequence[str],
    issues: Sequence[Mapping[str, Any]],
    reflection_summary: str,
    repair_instruction: str,
    repair_round: int,
    max_repair_rounds: int,
    allowed_agent_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "user_request": _latest_user_request(list(messages)),
        "task": {
            "task_id": "browser_preview_quality",
            "title": "Repair browser quality issues",
            "instruction": repair_instruction,
            "task_type": "repair",
            "expected_output": "\n".join(_dedupe_strings(checked_artifacts)),
        },
        "failure_source": "browser_preview_quality",
        "attempt_index": attempt_index,
        "failed_agent_id": failed_agent_id,
        "failed_state": TaskState.EVALUATION_FAILED.value,
        "failed_reason": reflection_summary,
        "failed_evaluators": ["browser_preview_quality"],
        "checked_artifacts": _dedupe_strings(checked_artifacts),
        "issues": _safe_issue_payloads(issues),
        "reflection_summary": _safe_text(reflection_summary, 400),
        "repair_instruction": _safe_text(repair_instruction, 1200),
        "repair_round": repair_round,
        "max_repair_rounds": max_repair_rounds,
        "allowed_agent_ids": list(allowed_agent_ids),
        "agent_candidates": _agent_candidates(
            config,
            run_context,
            allowed_agent_ids=allowed_agent_ids,
            excluded_agent_ids=set(),
        ),
        "required_output": {
            "action": "retry_current|fallback|finish_with_failure",
            "agent_id": "string|null",
            "reason": "short public reason",
            "summary": "optional short public summary",
        },
    }


def _parse_evaluator_repair_suggestion(payload: Mapping[str, Any]) -> _ParsedSuggestion:
    raw_action = payload.get("action")
    if not isinstance(raw_action, str):
        raise ValueError("evaluator_repair_llm_action_required")
    action = raw_action.strip()
    if action not in EVALUATOR_REPAIR_DECISION_ACTIONS:
        raise ValueError("evaluator_repair_llm_action_not_allowed")
    raw_reason = payload.get("reason")
    if not isinstance(raw_reason, str) or not raw_reason.strip():
        raise ValueError("evaluator_repair_llm_reason_required")
    raw_agent_id = payload.get("agent_id")
    if raw_agent_id is None:
        agent_id = None
    elif isinstance(raw_agent_id, str) and raw_agent_id.strip():
        agent_id = raw_agent_id.strip()
    else:
        raise ValueError("evaluator_repair_llm_agent_id_invalid")
    summary = payload.get("summary")
    return _ParsedSuggestion(
        action=action,
        agent_id=agent_id,
        reason=raw_reason.strip(),
        summary=summary.strip() if isinstance(summary, str) else "",
    )


def _rejected_evaluator_repair_decision(
    *,
    failure_source: str,
    attempt_index: int,
    failed_agent_id: str,
    failed_state: str,
    failed_evaluators: tuple[str, ...],
    checked_artifacts: tuple[str, ...],
    repair_round: int,
    allowed_agent_ids: tuple[str, ...],
    model_suggestion: dict[str, Any] | None,
    reason: str,
) -> EvaluatorRepairLlmDecision:
    return EvaluatorRepairLlmDecision(
        failure_source=failure_source,
        attempt_index=attempt_index,
        failed_agent_id=failed_agent_id,
        failed_state=failed_state,
        failed_evaluators=failed_evaluators,
        checked_artifacts=checked_artifacts,
        repair_round=repair_round,
        allowed_agent_ids=allowed_agent_ids,
        model_suggestion=model_suggestion,
        preferred_agent_id=None,
        allow_revisit=False,
        stop=False,
        status="fallback",
        decision_outcome="rejected",
        reason=reason,
    )


def _failure_source_from_results(results: list[Any]) -> str | None:
    for result in _failed_results(results):
        evaluator = result.get("evaluator")
        if isinstance(evaluator, str) and evaluator in SUPPORTED_EVALUATOR_REPAIR_SOURCES:
            return evaluator
    return None


def _failed_evaluators(results: list[Any]) -> list[str]:
    output: list[str] = []
    for result in _failed_results(results):
        evaluator = result.get("evaluator")
        if isinstance(evaluator, str) and evaluator:
            output.append(evaluator)
    return _dedupe_strings(output)


def _checked_artifacts(results: list[Any]) -> list[str]:
    artifacts: list[str] = []
    for result in _failed_results(results):
        checked = result.get("checked_artifacts")
        if isinstance(checked, list):
            artifacts.extend(item for item in checked if isinstance(item, str))
    return _dedupe_strings(artifacts)


def _failed_issues(results: list[Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for result in _failed_results(results):
        raw_issues = result.get("issues")
        if not isinstance(raw_issues, list):
            continue
        for issue in raw_issues:
            if not isinstance(issue, Mapping):
                continue
            issues.append(
                {
                    "code": _safe_text(str(issue.get("code") or ""), 120) or None,
                    "message": _safe_text(str(issue.get("message") or ""), 240) or None,
                    "evidence": _safe_text(str(issue.get("evidence") or ""), 240)
                    or None,
                    "repair_hint": _safe_text(
                        str(issue.get("repair_hint") or ""),
                        240,
                    )
                    or None,
                }
            )
    return issues[:12]


def _failed_results(results: list[Any]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for result in _evaluation_results_payload(results):
        if result.get("status") != "failed" and result.get("passed") is not False:
            continue
        failed.append(dict(result))
    return failed


def _reflection_summary(reflection: Any) -> str:
    payload = _reflection_payload(reflection)
    if isinstance(payload, Mapping):
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            return _safe_text(summary, 400)
    return ""


def _repair_instruction(reflection: Any) -> str:
    payload = _reflection_payload(reflection)
    if isinstance(payload, Mapping):
        instruction = payload.get("repair_instruction")
        if isinstance(instruction, str) and instruction.strip():
            return _safe_text(instruction, 1200)
    return ""


def _agent_candidates(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    *,
    allowed_agent_ids: Sequence[str],
    excluded_agent_ids: set[str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for agent_id in allowed_agent_ids:
        permitted = (
            agent_id not in excluded_agent_ids
            and _agent_permitted_for_attempt(config, run_context, agent_id)
        )
        output.append(
            {
                "agent_id": agent_id,
                "eligible_now": permitted,
                "eligibility_reason": _candidate_reason(
                    run_context,
                    agent_id,
                    excluded_agent_ids=excluded_agent_ids,
                ),
            }
        )
    return output


def _retry_current_allowed(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    agent_id: str,
    *,
    excluded_agent_ids: set[str],
) -> bool:
    if agent_id in excluded_agent_ids:
        return False
    return _agent_permitted_for_attempt(config, run_context, agent_id)


def _accepted_fallback_candidate(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    agent_id: str | None,
    *,
    allowed_agent_ids: tuple[str, ...],
    excluded_agent_ids: set[str],
    current_agent_id: str,
) -> tuple[str, bool, str] | None:
    if not isinstance(agent_id, str) or not agent_id.strip():
        return None
    candidate = agent_id.strip()
    if candidate not in allowed_agent_ids:
        return None
    if candidate in excluded_agent_ids:
        return None
    if candidate == current_agent_id:
        if _retry_current_allowed(
            config,
            run_context,
            candidate,
            excluded_agent_ids=excluded_agent_ids,
        ):
            return candidate, True, "remapped"
        return None
    if _agent_permitted_for_attempt(config, run_context, candidate):
        return candidate, False, "accepted"
    return None


def _finish_with_failure_allowed(
    *,
    repair_round: int,
    max_repair_rounds: int,
) -> bool:
    if max_repair_rounds <= 0:
        return True
    return repair_round + 1 >= max_repair_rounds


def _candidate_reason(
    run_context: OrchestratorRunContext,
    agent_id: str,
    *,
    excluded_agent_ids: set[str],
) -> str:
    if agent_id in excluded_agent_ids:
        return "review_excluded"
    if agent_id in run_context.failed_runtime_agent_ids:
        return "runtime_failed_in_run"
    if runtime_cooldown_status(agent_id)[0] == "cooldown":
        return "cooldown"
    return "eligible"


def _model_suggestion_payload(suggestion: _ParsedSuggestion) -> dict[str, Any]:
    return {
        "action": suggestion.action,
        "agent_id": suggestion.agent_id,
        "reason": _safe_text(suggestion.reason, 240),
        "summary": _safe_text(suggestion.summary, 240) or None,
    }


def _safe_issue_payloads(issues: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for issue in issues:
        output.append(
            {
                "code": _safe_text(str(issue.get("code") or ""), 120) or None,
                "message": _safe_text(str(issue.get("message") or ""), 240) or None,
                "evidence": _safe_text(str(issue.get("evidence") or ""), 240) or None,
                "repair_hint": _safe_text(
                    str(issue.get("repair_hint") or ""),
                    240,
                )
                or None,
            }
        )
    return output[:12]


def _safe_failed_reason(text: str) -> str:
    redacted = text.replace("\r", " ").replace("\n", " ").strip()
    redacted = redacted.replace("stderr:", "").replace("OpenAI Codex", "runtime")
    return _safe_text(redacted, 240)


def _decision_summary(
    decision: EvaluatorRepairLlmDecision,
    *,
    backend_action: str,
    backend_agent_id: str | None,
) -> str:
    suggestion_action = None
    if isinstance(decision.model_suggestion, Mapping):
        raw = decision.model_suggestion.get("action")
        if isinstance(raw, str) and raw.strip():
            suggestion_action = raw.strip()
    target = f"@{backend_agent_id}" if backend_agent_id else "no next agent"
    if decision.status == "succeeded":
        verb = (
            "accepted"
            if decision.decision_outcome == "accepted"
            else "remapped"
        )
    else:
        verb = "fell back"
    suggestion = suggestion_action or "none"
    return (
        f"Repair suggestion for {decision.failure_source} {verb}: "
        f"{suggestion} -> {backend_action} via {target}."
    )


def _model_failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "evaluator_repair_llm_unavailable"
    if message in {
        "empty_evaluator_repair_llm_decision",
        "evaluator_repair_llm_action_not_allowed",
        "evaluator_repair_llm_action_required",
        "evaluator_repair_llm_reason_required",
        "evaluator_repair_llm_agent_id_invalid",
        "evaluator_repair_llm_decision_must_be_object",
    }:
        return message
    return "evaluator_repair_llm_unavailable"


def _safe_text(value: str | None, max_chars: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."
