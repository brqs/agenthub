"""Safe observability helpers for Orchestrator LLM control points."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

from app.agents.orchestrator._internal.memory import record_event as _memory_record_event
from app.agents.orchestrator.types import OrchestratorRunContext

LLM_CONTROL_POINT_EVENT = "llm_control_point"
PENDING_LLM_CONTROL_POINTS_KEY = "_llm_control_points"


def model_backend_for_phase(config: Mapping[str, Any], phase: str) -> str:
    if phase == "planner" and config.get("planner_gateway") is not None:
        return "test_gateway"
    if phase == "react_replanner" and (
        config.get("react_gateway") is not None
        or config.get("replanner_gateway") is not None
    ):
        return "test_gateway"
    if phase == "dialogue_controller" and config.get("dialogue_gateway") is not None:
        return "test_gateway"
    if phase == "tool_loop" and config.get("orchestrator_tool_gateway") is not None:
        return "test_gateway"
    if (
        phase == "response_polish"
        and config.get("orchestrator_response_polish_gateway") is not None
    ):
        return "test_gateway"

    if phase in {"planner", "react_replanner"}:
        backend = config.get("planner_model_backend", config.get("model_backend", "claude"))
    elif phase == "dialogue_controller":
        backend = config.get("dialogue_model_backend", config.get("model_backend", "claude"))
    elif phase == "response_polish":
        backend = config.get(
            "orchestrator_response_polish_model_backend",
            config.get("model_backend", "claude"),
        )
    else:
        backend = config.get("model_backend", "claude")
    return str(backend or "unknown")


def append_pending_llm_control_point(
    config: Mapping[str, Any],
    *,
    phase: str,
    status: str,
    used_llm: bool,
    model_backend: str | None = None,
    fallback_reason: str | None = None,
    decision_summary: str | None = None,
) -> None:
    if not isinstance(config, MutableMapping):
        return
    points = config.setdefault(PENDING_LLM_CONTROL_POINTS_KEY, [])
    if not isinstance(points, list):
        points = []
        config[PENDING_LLM_CONTROL_POINTS_KEY] = points
    points.append(
        make_llm_control_point(
            phase=phase,
            status=status,
            used_llm=used_llm,
            model_backend=model_backend or model_backend_for_phase(config, phase),
            fallback_reason=fallback_reason,
            decision_summary=decision_summary,
        )
    )


async def record_llm_control_point(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    *,
    phase: str,
    status: str,
    used_llm: bool,
    model_backend: str | None = None,
    fallback_reason: str | None = None,
    decision_summary: str | None = None,
) -> None:
    point = make_llm_control_point(
        phase=phase,
        status=status,
        used_llm=used_llm,
        model_backend=model_backend or model_backend_for_phase(config, phase),
        fallback_reason=fallback_reason,
        decision_summary=decision_summary,
    )
    run_context.llm_control_points.append(point)
    await _memory_record_event(
        config,
        run_context,
        event_type=LLM_CONTROL_POINT_EVENT,
        agent_id="orchestrator",
        payload=point,
    )


async def flush_pending_llm_control_points(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
) -> None:
    if not isinstance(config, MutableMapping):
        return
    raw_points = config.get(PENDING_LLM_CONTROL_POINTS_KEY)
    if not isinstance(raw_points, list):
        return
    config[PENDING_LLM_CONTROL_POINTS_KEY] = []
    for raw in raw_points:
        if not isinstance(raw, Mapping):
            continue
        point = make_llm_control_point(
            phase=str(raw.get("phase") or "unknown"),
            status=str(raw.get("status") or "unknown"),
            used_llm=raw.get("used_llm") is True,
            model_backend=str(raw.get("model_backend") or "unknown"),
            fallback_reason=_optional_text(raw.get("fallback_reason")),
            decision_summary=_optional_text(raw.get("decision_summary")),
        )
        run_context.llm_control_points.append(point)
        await _memory_record_event(
            config,
            run_context,
            event_type=LLM_CONTROL_POINT_EVENT,
            agent_id="orchestrator",
            payload=point,
        )


def make_llm_control_point(
    *,
    phase: str,
    status: str,
    used_llm: bool,
    model_backend: str,
    fallback_reason: str | None,
    decision_summary: str | None,
) -> dict[str, Any]:
    return {
        "phase": _safe_text(phase, 64) or "unknown",
        "model_backend": _safe_text(model_backend, 64) or "unknown",
        "status": _safe_text(status, 64) or "unknown",
        "used_llm": bool(used_llm),
        "fallback_reason": _safe_text(fallback_reason, 240) if fallback_reason else None,
        "decision_summary": (
            _safe_text(decision_summary, 400) if decision_summary else None
        ),
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _safe_text(value: str | None, max_chars: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."
