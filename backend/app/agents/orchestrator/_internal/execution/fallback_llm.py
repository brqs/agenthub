"""LLM suggestion helper for per-task fallback selection."""

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
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage

TASK_FALLBACK_DECISION_ACTIONS = frozenset(
    {"retry_original", "fallback", "add_repair", "stop"}
)
TASK_FALLBACK_DECISION_SYSTEM_PROMPT = (
    "You are AgentHub's Orchestrator fallback advisor. Return strict JSON only. "
    "Do not include markdown. Do not include thought, chain_of_thought, hidden "
    "reasoning, private analysis, prompt text, tokens, stderr, env, or secrets. "
    "Choose action only from retry_original, fallback, add_repair, stop. "
    "You may only reference agent ids from the provided allowed_agent_ids list."
)


@dataclass(frozen=True, slots=True)
class TaskFallbackLlmDecision:
    attempt_index: int
    failed_agent_id: str
    failed_state: str
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


def task_fallback_llm_decision_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_llm_fallback_decision_enabled") is True


async def maybe_task_fallback_llm_decision(
    config: Mapping[str, Any],
    *,
    task: SubTask,
    messages: Sequence[ChatMessage],
    task_result: TaskResult,
    fallback_agents: list[str],
    max_attempts: int,
    run_context: OrchestratorRunContext,
    excluded_agent_ids: set[str],
) -> TaskFallbackLlmDecision | None:
    if not task_fallback_llm_decision_enabled(config):
        return None
    if task_result.final_state not in {
        TaskState.FAILED,
        TaskState.ARTIFACT_MISSING,
        TaskState.EVALUATION_FAILED,
    }:
        return None
    if not task_result.attempts or len(task_result.attempts) >= max_attempts:
        return None

    failed_attempt = task_result.attempts[-1]
    allowed_agent_ids = tuple(_fallback_allowed_agent_ids(task, fallback_agents))
    try:
        suggestion_payload = await _task_fallback_decision_payload(
            config,
            messages=list(messages),
            task=task,
            task_result=task_result,
            failed_attempt=failed_attempt,
            fallback_agents=fallback_agents,
            max_attempts=max_attempts,
            run_context=run_context,
            excluded_agent_ids=excluded_agent_ids,
        )
        suggestion = _parse_task_fallback_suggestion(suggestion_payload)
    except Exception as exc:  # noqa: BLE001
        return TaskFallbackLlmDecision(
            attempt_index=failed_attempt.attempt_index,
            failed_agent_id=failed_attempt.agent_id,
            failed_state=task_result.final_state.value,
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
    if suggestion.action == "stop":
        return TaskFallbackLlmDecision(
            attempt_index=failed_attempt.attempt_index,
            failed_agent_id=failed_attempt.agent_id,
            failed_state=task_result.final_state.value,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=raw_model_suggestion,
            preferred_agent_id=None,
            allow_revisit=False,
            stop=True,
            status="succeeded",
            decision_outcome="accepted",
            reason=_safe_text(suggestion.reason, 240) or "llm_requested_stop",
        )

    if suggestion.action == "retry_original":
        if _retry_original_allowed(
            config,
            run_context,
            failed_attempt.agent_id,
            excluded_agent_ids=excluded_agent_ids,
        ):
            return TaskFallbackLlmDecision(
                attempt_index=failed_attempt.attempt_index,
                failed_agent_id=failed_attempt.agent_id,
                failed_state=task_result.final_state.value,
                allowed_agent_ids=allowed_agent_ids,
                model_suggestion=raw_model_suggestion,
                preferred_agent_id=failed_attempt.agent_id,
                allow_revisit=True,
                stop=False,
                status="succeeded",
                decision_outcome="accepted",
                reason=_safe_text(suggestion.reason, 240) or "retry_original",
            )
        return _rejected_task_fallback_decision(
            failed_attempt=failed_attempt,
            task_result=task_result,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=raw_model_suggestion,
            reason="retry_original_not_available",
        )

    if suggestion.action == "fallback":
        remapped = _accepted_fallback_candidate(
            config,
            run_context,
            task,
            suggestion.agent_id,
            allowed_agent_ids=allowed_agent_ids,
            excluded_agent_ids=excluded_agent_ids,
        )
        if remapped is not None:
            preferred_agent_id, allow_revisit, outcome = remapped
            return TaskFallbackLlmDecision(
                attempt_index=failed_attempt.attempt_index,
                failed_agent_id=failed_attempt.agent_id,
                failed_state=task_result.final_state.value,
                allowed_agent_ids=allowed_agent_ids,
                model_suggestion=raw_model_suggestion,
                preferred_agent_id=preferred_agent_id,
                allow_revisit=allow_revisit,
                stop=False,
                status="succeeded",
                decision_outcome=outcome,
                reason=_safe_text(suggestion.reason, 240) or "fallback",
            )
        return _rejected_task_fallback_decision(
            failed_attempt=failed_attempt,
            task_result=task_result,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=raw_model_suggestion,
            reason="suggested_agent_not_allowed",
        )

    if suggestion.action == "add_repair":
        remapped = _accepted_fallback_candidate(
            config,
            run_context,
            task,
            suggestion.agent_id,
            allowed_agent_ids=allowed_agent_ids,
            excluded_agent_ids=excluded_agent_ids,
        )
        if remapped is not None:
            preferred_agent_id, allow_revisit, _ = remapped
            return TaskFallbackLlmDecision(
                attempt_index=failed_attempt.attempt_index,
                failed_agent_id=failed_attempt.agent_id,
                failed_state=task_result.final_state.value,
                allowed_agent_ids=allowed_agent_ids,
                model_suggestion=raw_model_suggestion,
                preferred_agent_id=preferred_agent_id,
                allow_revisit=allow_revisit,
                stop=False,
                status="succeeded",
                decision_outcome="remapped",
                reason=_safe_text(suggestion.reason, 240) or "add_repair",
            )
        return _rejected_task_fallback_decision(
            failed_attempt=failed_attempt,
            task_result=task_result,
            allowed_agent_ids=allowed_agent_ids,
            model_suggestion=raw_model_suggestion,
            reason="repair_agent_not_allowed",
        )

    return _rejected_task_fallback_decision(
        failed_attempt=failed_attempt,
        task_result=task_result,
        allowed_agent_ids=allowed_agent_ids,
        model_suggestion=raw_model_suggestion,
        reason="unsupported_fallback_action",
    )


async def record_task_fallback_llm_decision(
    config: Mapping[str, Any],
    *,
    run_context: OrchestratorRunContext,
    task_id: str,
    decision: TaskFallbackLlmDecision,
    backend_action: str,
    backend_agent_id: str | None,
    record_event: Any,
) -> None:
    await record_event(
        config,
        run_context,
        event_type="task_fallback_llm_decision",
        task_id=task_id,
        agent_id="orchestrator",
        payload={
            "attempt_index": decision.attempt_index,
            "failed_agent_id": decision.failed_agent_id,
            "failed_state": decision.failed_state,
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


async def _task_fallback_decision_payload(
    config: Mapping[str, Any],
    *,
    messages: list[ChatMessage],
    task: SubTask,
    task_result: TaskResult,
    failed_attempt: TaskAttempt,
    fallback_agents: list[str],
    max_attempts: int,
    run_context: OrchestratorRunContext,
    excluded_agent_ids: set[str],
) -> dict[str, Any]:
    gateway = _react_gateway(
        config,
        _positive_int_config,
        TASK_FALLBACK_DECISION_SYSTEM_PROMPT,
    )
    parts: list[str] = []
    async for chunk in gateway.stream(
        [
            ChatMessage(
                role="user",
                content=json.dumps(
                    _task_fallback_prompt_payload(
                        config=config,
                        messages=messages,
                        task=task,
                        task_result=task_result,
                        failed_attempt=failed_attempt,
                        fallback_agents=fallback_agents,
                        max_attempts=max_attempts,
                        run_context=run_context,
                        excluded_agent_ids=excluded_agent_ids,
                    ),
                    ensure_ascii=False,
                ),
            )
        ],
        system_prompt=TASK_FALLBACK_DECISION_SYSTEM_PROMPT,
        config=_react_config(config, _positive_int_config),
    ):
        if chunk.event_type == "delta":
            parts.append(chunk.text_delta or chunk.code_delta or "")
        elif chunk.event_type == "error":
            raise ValueError(chunk.error_code or chunk.error or "fallback_llm_error")
    text = "".join(parts).strip()
    if not text:
        raise ValueError("empty_fallback_llm_decision")
    payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise ValueError("fallback_llm_decision_must_be_object")
    return dict(payload)


def _task_fallback_prompt_payload(
    *,
    config: Mapping[str, Any],
    messages: Sequence[ChatMessage],
    task: SubTask,
    task_result: TaskResult,
    failed_attempt: TaskAttempt,
    fallback_agents: list[str],
    max_attempts: int,
    run_context: OrchestratorRunContext,
    excluded_agent_ids: set[str],
) -> dict[str, Any]:
    allowed_agent_ids = _fallback_allowed_agent_ids(task, fallback_agents)
    agent_candidates = []
    for agent_id in allowed_agent_ids:
        permitted = (
            agent_id not in excluded_agent_ids
            and _agent_permitted_for_attempt(config, run_context, agent_id)
        )
        agent_candidates.append(
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
    return {
        "user_request": _latest_user_request(list(messages)),
        "task": {
            "task_id": task.task_id,
            "title": task.title,
            "instruction": task.instruction,
            "task_type": task.task_type,
            "expected_output": task.expected_output,
        },
        "attempt_index": failed_attempt.attempt_index,
        "max_task_attempts": max_attempts,
        "failed_state": task_result.final_state.value,
        "failed_agent_id": failed_attempt.agent_id,
        "failed_reason": _safe_failed_reason(failed_attempt.error or ""),
        "allowed_agent_ids": allowed_agent_ids,
        "agent_candidates": agent_candidates,
        "fallback_agents": fallback_agents,
        "required_output": {
            "action": "retry_original|fallback|add_repair|stop",
            "agent_id": "string|null",
            "reason": "short public reason",
            "summary": "optional short public summary",
        },
    }


def _parse_task_fallback_suggestion(payload: Mapping[str, Any]) -> _ParsedSuggestion:
    raw_action = payload.get("action")
    if not isinstance(raw_action, str):
        raise ValueError("fallback_llm_action_required")
    action = raw_action.strip()
    if action not in TASK_FALLBACK_DECISION_ACTIONS:
        raise ValueError("fallback_llm_action_not_allowed")
    raw_reason = payload.get("reason")
    if not isinstance(raw_reason, str) or not raw_reason.strip():
        raise ValueError("fallback_llm_reason_required")
    raw_agent_id = payload.get("agent_id")
    if raw_agent_id is None:
        agent_id = None
    elif isinstance(raw_agent_id, str) and raw_agent_id.strip():
        agent_id = raw_agent_id.strip()
    else:
        raise ValueError("fallback_llm_agent_id_invalid")
    summary = payload.get("summary")
    return _ParsedSuggestion(
        action=action,
        agent_id=agent_id,
        reason=raw_reason.strip(),
        summary=summary.strip() if isinstance(summary, str) else "",
    )


def _rejected_task_fallback_decision(
    *,
    failed_attempt: TaskAttempt,
    task_result: TaskResult,
    allowed_agent_ids: tuple[str, ...],
    model_suggestion: dict[str, Any] | None,
    reason: str,
) -> TaskFallbackLlmDecision:
    return TaskFallbackLlmDecision(
        attempt_index=failed_attempt.attempt_index,
        failed_agent_id=failed_attempt.agent_id,
        failed_state=task_result.final_state.value,
        allowed_agent_ids=allowed_agent_ids,
        model_suggestion=model_suggestion,
        preferred_agent_id=None,
        allow_revisit=False,
        stop=False,
        status="fallback",
        decision_outcome="rejected",
        reason=reason,
    )


def _fallback_allowed_agent_ids(task: SubTask, fallback_agents: list[str]) -> list[str]:
    return _dedupe_strings([task.agent_id, *fallback_agents])


def _retry_original_allowed(
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
    task: SubTask,
    agent_id: str | None,
    *,
    allowed_agent_ids: tuple[str, ...],
    excluded_agent_ids: set[str],
) -> tuple[str, bool, str] | None:
    if not isinstance(agent_id, str) or not agent_id.strip():
        return None
    candidate = agent_id.strip()
    if candidate not in allowed_agent_ids:
        return None
    if candidate in excluded_agent_ids:
        return None
    if candidate == task.agent_id:
        if _retry_original_allowed(
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
    return "eligible"


def _model_suggestion_payload(suggestion: _ParsedSuggestion) -> dict[str, Any]:
    return {
        "action": suggestion.action,
        "agent_id": suggestion.agent_id,
        "reason": _safe_text(suggestion.reason, 240),
        "summary": _safe_text(suggestion.summary, 240) or None,
    }


def _decision_summary(
    decision: TaskFallbackLlmDecision,
    *,
    backend_action: str,
    backend_agent_id: str | None,
) -> str:
    suggestion_action = None
    if isinstance(decision.model_suggestion, Mapping):
        raw_action = decision.model_suggestion.get("action")
        if isinstance(raw_action, str):
            suggestion_action = raw_action
    if decision.decision_outcome == "deterministic_fallback":
        return _single_line(
            f"Fallback decision unavailable; backend used {backend_action}"
            f"{_agent_phrase(backend_agent_id)}."
        )
    if decision.decision_outcome == "rejected":
        return _single_line(
            f"Fallback suggestion rejected; backend used {backend_action}"
            f"{_agent_phrase(backend_agent_id)}."
        )
    if decision.decision_outcome == "remapped":
        return _single_line(
            f"Fallback suggestion {suggestion_action or 'unknown'} remapped to "
            f"{backend_action}{_agent_phrase(backend_agent_id)}."
        )
    if suggestion_action == "stop":
        return "Fallback suggestion accepted: stop automatic retry."
    return _single_line(
        f"Fallback suggestion accepted: {backend_action}{_agent_phrase(backend_agent_id)}."
    )


def _agent_phrase(agent_id: str | None) -> str:
    if not agent_id:
        return ""
    return f" using @{agent_id}"


def _model_failure_reason(exc: Exception) -> str:
    lowered = str(exc or "").lower()
    if "empty" in lowered:
        return "empty_fallback_llm_decision"
    if "json" in lowered:
        return "invalid_fallback_llm_json"
    if "timeout" in lowered:
        return "fallback_llm_timeout"
    return "fallback_llm_unavailable"


def _safe_failed_reason(reason: str) -> str:
    lowered = str(reason or "").lower()
    if not lowered:
        return "no_public_failure_reason"
    if "timeout" in lowered:
        return "task attempt timed out"
    if any(marker in lowered for marker in ("permission denied", "[errno", "auth", "claude.json")):
        return "runtime auth or permission issue"
    if "missing" in lowered or "artifact" in lowered:
        return "expected artifact missing"
    if "evaluation" in lowered:
        return "evaluation failed"
    return "task attempt did not meet acceptance requirements"


def _single_line(text: str) -> str:
    return " ".join(text.split())


def _safe_text(value: Any, max_chars: int) -> str:
    text = _single_line(str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."
