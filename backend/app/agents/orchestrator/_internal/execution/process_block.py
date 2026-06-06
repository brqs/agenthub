"""Safe public process summary block for Orchestrator responses."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.agents.orchestrator.evaluation import evaluation_results_payload
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk

MAX_STEPS = 20
MAX_LABEL_CHARS = 80
MAX_DETAIL_CHARS = 240
MAX_SUMMARY_CHARS = 400

FORBIDDEN_PROCESS_PATTERNS = (
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
    "stderr",
    "Traceback",
)

KIND_VALUES = {
    "routing",
    "planning",
    "dispatch",
    "tool",
    "review",
    "evaluation",
    "workflow",
    "deployment",
    "artifact",
    "repair",
    "summary",
}


def process_block_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_process_block_enabled", True) is not False


def process_block_chunks(
    config: Mapping[str, Any],
    block_index: int,
    payload: Mapping[str, Any],
) -> tuple[tuple[StreamChunk, int], ...]:
    if not process_block_enabled(config):
        return ()
    next_block_index = block_index + 1
    return (
        (
            StreamChunk(
                event_type="block_start",
                block_index=block_index,
                block_type="process",
                agent_id="orchestrator",
                metadata=sanitize_process_payload(payload),
            ),
            next_block_index,
        ),
        (
            StreamChunk(
                event_type="block_end",
                block_index=block_index,
                agent_id="orchestrator",
            ),
            next_block_index,
        ),
    )


def process_block_start(
    config: Mapping[str, Any],
    block_index: int,
    payload: Mapping[str, Any] | None = None,
) -> tuple[StreamChunk, int] | None:
    if not process_block_enabled(config):
        return None
    clean = sanitize_process_payload(payload or _empty_process_payload())
    clean["steps"] = []
    clean.pop("summary", None)
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="process",
            agent_id="orchestrator",
            metadata=clean,
        ),
        block_index + 1,
    )


def process_block_end(
    config: Mapping[str, Any],
    block_index: int | None,
) -> StreamChunk | None:
    if block_index is None or not process_block_enabled(config):
        return None
    return StreamChunk(
        event_type="block_end",
        block_index=block_index,
        agent_id="orchestrator",
    )


def process_step_delta(
    config: Mapping[str, Any],
    block_index: int | None,
    step: Mapping[str, Any],
) -> StreamChunk | None:
    if block_index is None or not process_block_enabled(config):
        return None
    sanitized = _sanitize_step(step)
    if sanitized is None:
        return None
    return StreamChunk(
        event_type="delta",
        block_index=block_index,
        agent_id="orchestrator",
        metadata={"process_delta": {"op": "upsert_step", "step": sanitized}},
    )


def process_summary_delta(
    config: Mapping[str, Any],
    block_index: int | None,
    *,
    status: str,
    summary: str,
) -> StreamChunk | None:
    if block_index is None or not process_block_enabled(config):
        return None
    clean_status = _process_status(status)
    clean_summary = _clean_text(summary, MAX_SUMMARY_CHARS)
    return StreamChunk(
        event_type="delta",
        block_index=block_index,
        agent_id="orchestrator",
        metadata={
            "process_delta": {
                "op": "set_summary",
                "status": clean_status,
                "summary": clean_summary,
            }
        },
    )


def agent_process_block_start(
    config: Mapping[str, Any],
    block_index: int,
    *,
    agent_id: str,
    title: str = "思考与执行",
) -> tuple[StreamChunk, int] | None:
    if not process_block_enabled(config):
        return None
    clean = sanitize_process_payload(
        {
            "type": "process",
            "agent_id": agent_id,
            "title": title,
            "status": "running",
            "default_collapsed": False,
            "steps": [],
            "metadata": {"source": "agent_process"},
        }
    )
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="process",
            agent_id=agent_id,
            metadata=clean,
        ),
        block_index + 1,
    )


def agent_process_block_end(
    config: Mapping[str, Any],
    block_index: int | None,
    *,
    agent_id: str,
) -> StreamChunk | None:
    if block_index is None or not process_block_enabled(config):
        return None
    return StreamChunk(
        event_type="block_end",
        block_index=block_index,
        agent_id=agent_id,
    )


def agent_process_step_delta(
    config: Mapping[str, Any],
    block_index: int | None,
    *,
    agent_id: str,
    step: Mapping[str, Any],
) -> StreamChunk | None:
    if block_index is None or not process_block_enabled(config):
        return None
    sanitized = _sanitize_step({**step, "agent_id": agent_id})
    if sanitized is None:
        return None
    return StreamChunk(
        event_type="delta",
        block_index=block_index,
        agent_id=agent_id,
        metadata={"process_delta": {"op": "upsert_step", "step": sanitized}},
    )


def agent_process_summary_delta(
    config: Mapping[str, Any],
    block_index: int | None,
    *,
    agent_id: str,
    status: str,
    summary: str,
) -> StreamChunk | None:
    if block_index is None or not process_block_enabled(config):
        return None
    return StreamChunk(
        event_type="delta",
        block_index=block_index,
        agent_id=agent_id,
        metadata={
            "process_delta": {
                "op": "set_summary",
                "status": _process_status(status),
                "summary": _clean_text(summary, MAX_SUMMARY_CHARS),
            }
        },
    )


def agent_task_process_step(
    task: SubTask,
    *,
    agent_id: str,
    status: str,
    detail: str,
) -> dict[str, Any]:
    return _public_step(
        _public_task_step_id(task),
        task.title,
        _task_kind(task),
        status,
        detail,
        agent_id=agent_id,
    )


def route_process_step(
    route: str,
    *,
    status: str = "done",
    detail: str | None = None,
) -> dict[str, Any]:
    label, fallback_detail = _route_labels(route)
    final_status = "error" if _process_status(status) == "error" else "done"
    return _public_step(
        "route",
        label,
        "routing",
        final_status,
        detail or fallback_detail,
    )


def planning_process_step(tasks: Sequence[SubTask]) -> dict[str, Any]:
    return _public_step(
        "planning",
        "拆解任务并安排执行顺序",
        "planning",
        "done",
        f"共 {len(tasks)} 个公开执行步骤。",
    )


def task_running_step(task: SubTask) -> dict[str, Any]:
    return _public_step(
        _public_task_step_id(task),
        task.title,
        _task_kind(task),
        "running",
        "正在执行。",
        agent_id=task.agent_id,
    )


def task_result_step(
    task: SubTask,
    state: TaskState,
    result: TaskResult | None = None,
) -> dict[str, Any]:
    step = _task_step(task, state, result)
    step["id"] = _public_task_step_id(task)
    return step


def skipped_task_step(task: SubTask) -> dict[str, Any]:
    return task_result_step(task, TaskState.SKIPPED, None)


def final_process_deltas(
    config: Mapping[str, Any],
    block_index: int | None,
    payload: Mapping[str, Any],
) -> tuple[StreamChunk, ...]:
    if block_index is None or not process_block_enabled(config):
        return ()
    clean = sanitize_process_payload(payload)
    chunks: list[StreamChunk] = []
    for index, step in enumerate(clean.get("steps", [])):
        if not isinstance(step, Mapping):
            continue
        step_payload = dict(step)
        step_payload.setdefault("id", _fallback_step_id(index, step_payload))
        chunk = process_step_delta(config, block_index, step_payload)
        if chunk is not None:
            chunks.append(chunk)
    summary = clean.get("summary")
    if isinstance(summary, str):
        chunk = process_summary_delta(
            config,
            block_index,
            status=str(clean.get("status") or "done"),
            summary=summary,
        )
        if chunk is not None:
            chunks.append(chunk)
    return tuple(chunks)


def route_process_block(
    route: str,
    messages: Sequence[ChatMessage],
    *,
    status: str = "done",
    detail: str | None = None,
) -> dict[str, Any]:
    label, fallback_detail = _route_labels(route)
    final_status = _process_status(status)
    return sanitize_process_payload(
        {
            "type": "process",
            "agent_id": "orchestrator",
            "title": _title(messages),
            "status": final_status,
            "default_collapsed": False,
            "steps": [
                {
                    "label": label,
                    "kind": "routing",
                    "status": "error" if final_status == "error" else "done",
                    "detail": detail or fallback_detail,
                }
            ],
            "summary": _status_summary(final_status, messages),
            "metadata": {"source": "orchestrator_process", "route": route},
        }
    )


def execution_process_block(
    messages: Sequence[ChatMessage],
    tasks: Sequence[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext,
    *,
    tool_results: Sequence[Any] = (),
) -> dict[str, Any]:
    effective_states = _effective_states(tasks, task_states, run_context)
    status = _overall_process_status(effective_states.values(), run_context, tool_results)
    steps: list[dict[str, Any]] = []
    if tasks:
        steps.append(
            {
                "label": "拆解任务并安排执行顺序",
                "kind": "planning",
                "status": "done",
                "detail": f"共 {len(tasks)} 个公开执行步骤。",
            }
        )
    elif tool_results:
        steps.append(
            {
                "label": "选择工具执行路径",
                "kind": "planning",
                "status": "done",
                "detail": "通过平台或工作区工具处理本次请求。",
            }
        )

    for task in tasks:
        state = effective_states.get(task.task_id, TaskState.PENDING)
        result = run_context.results.get(task.task_id)
        steps.append(_task_step(task, state, result))

    for step in _result_summary_steps(run_context, tool_results):
        steps.append(step)

    if not steps:
        steps.append(
            {
                "label": "整理执行结果",
                "kind": "summary",
                "status": "done" if status == "done" else "error",
                "detail": "本次请求没有生成可公开的任务拆解步骤。",
            }
        )

    return sanitize_process_payload(
        {
            "type": "process",
            "agent_id": "orchestrator",
            "title": _title(messages),
            "status": status,
            "default_collapsed": False,
            "steps": steps[:MAX_STEPS],
            "summary": _status_summary(status, messages),
            "metadata": {"source": "orchestrator_process"},
        }
    )


def sanitize_process_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    status = _process_status(payload.get("status"))
    metadata = payload.get("metadata")
    clean: dict[str, Any] = {
        "type": "process",
        "agent_id": _clean_optional(payload.get("agent_id"), 80) or "orchestrator",
        "title": _clean_text(payload.get("title") or "思考与执行", MAX_LABEL_CHARS),
        "status": status,
        "default_collapsed": bool(payload.get("default_collapsed", False)),
        "steps": [],
        "metadata": _safe_metadata(metadata),
    }
    summary = _clean_optional(payload.get("summary"), MAX_SUMMARY_CHARS)
    if summary:
        clean["summary"] = summary
    for raw_step in payload.get("steps", []):
        if not isinstance(raw_step, Mapping):
            continue
        label = _clean_text(raw_step.get("label") or "执行步骤", MAX_LABEL_CHARS)
        detail = _clean_optional(raw_step.get("detail"), MAX_DETAIL_CHARS)
        step = {
            "label": label,
            "kind": _step_kind(raw_step.get("kind")),
            "status": _step_status(raw_step.get("status")),
        }
        step_id = _clean_step_id(raw_step.get("id"))
        if step_id:
            step["id"] = step_id
        if detail:
            step["detail"] = detail
        agent_id = _clean_optional(raw_step.get("agent_id"), 80)
        if agent_id:
            step["agent_id"] = agent_id
        clean["steps"].append(step)
        if len(clean["steps"]) >= MAX_STEPS:
            break
    return clean


def contains_forbidden_process_text(payload: Mapping[str, Any]) -> bool:
    text = str(payload)
    lowered = text.lower()
    if any(pattern.lower() in lowered for pattern in FORBIDDEN_PROCESS_PATTERNS):
        return True
    return bool(re.search(r"\b(?:call[_-]|orch\.)[\w.-]+", text))


def _route_labels(route: str) -> tuple[str, str]:
    labels = {
        "platform_fact": ("判断这是平台信息问题", "直接根据当前平台配置组织回答。"),
        "direct_answer": ("判断这是直接问答", "无需拆解任务，直接生成面向用户的回答。"),
        "custom_agent": ("判断这是自定义 Agent 请求", "调用平台工具处理 Agent 创建请求。"),
        "fallback": ("使用可用 Agent 处理请求", "计划生成不可用时，交给可用执行方处理。"),
    }
    return labels.get(route, ("选择响应路径", "根据请求类型选择合适的响应方式。"))


def _empty_process_payload() -> dict[str, Any]:
    return {
        "type": "process",
        "agent_id": "orchestrator",
        "title": "思考与执行",
        "status": "running",
        "default_collapsed": False,
        "steps": [],
        "metadata": {"source": "orchestrator_process"},
    }


def _sanitize_step(raw_step: Mapping[str, Any]) -> dict[str, Any] | None:
    clean = sanitize_process_payload(
        {
            **_empty_process_payload(),
            "steps": [raw_step],
        }
    )
    steps = clean.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    step = steps[0]
    return dict(step) if isinstance(step, Mapping) else None


def _public_step(
    step_id: str,
    label: str,
    kind: str,
    status: str,
    detail: str | None = None,
    *,
    agent_id: str | None = None,
) -> dict[str, Any]:
    step: dict[str, Any] = {
        "id": step_id,
        "label": label,
        "kind": kind,
        "status": status,
    }
    if detail:
        step["detail"] = detail
    if agent_id:
        step["agent_id"] = agent_id
    return step


def _task_step(task: SubTask, state: TaskState, result: TaskResult | None) -> dict[str, Any]:
    status = _state_to_step_status(state)
    detail = _task_detail(state, result)
    step: dict[str, Any] = {
        "label": task.title,
        "kind": _task_kind(task),
        "status": status,
        "detail": detail,
    }
    agent_id = _final_agent_id(task, result)
    if agent_id:
        step["agent_id"] = agent_id
    return step


def _public_task_step_id(task: SubTask) -> str:
    title = re.sub(r"[^a-z0-9]+", "-", task.title.lower()).strip("-")
    if title:
        return f"step-{title[:32]}"
    return "step"


def _fallback_step_id(index: int, step: Mapping[str, Any]) -> str:
    kind = _step_kind(step.get("kind"))
    label = _clean_text(step.get("label") or kind, 32)
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f"{kind}-{slug or index + 1}"


def _result_summary_steps(
    run_context: OrchestratorRunContext,
    tool_results: Sequence[Any],
) -> list[dict[str, Any]]:
    artifacts: list[str] = []
    changed_files: list[str] = []
    reviews: list[str] = []
    evaluation_passed = 0
    evaluation_failed = 0
    workflow_seen = False
    for result in run_context.results.values():
        for attempt in result.attempts:
            artifacts.extend(attempt.artifact_paths)
            changed_files.extend(attempt.file_changes.get("created", []))
            changed_files.extend(attempt.file_changes.get("modified", []))
            if attempt.review_outcome:
                reviews.append(_review_label(attempt.review_outcome))
            for payload in evaluation_results_payload(attempt.evaluation_results):
                if payload.get("evaluator") == "workflow_dry_run":
                    workflow_seen = True
                if payload.get("status") == "failed":
                    evaluation_failed += 1
                elif payload.get("passed") is True and payload.get("status") != "skipped":
                    evaluation_passed += 1

    steps: list[dict[str, Any]] = []
    unique_artifacts = _dedupe([*artifacts, *changed_files])
    if unique_artifacts:
        steps.append(
            {
                "label": "整理文件和产物",
                "kind": "artifact",
                "status": "done",
                "detail": _join_preview(unique_artifacts),
            }
        )
    if evaluation_passed or evaluation_failed:
        steps.append(
            {
                "label": "执行验证检查",
                "kind": "evaluation",
                "status": "error" if evaluation_failed else "done",
                "detail": f"{evaluation_passed} 项通过，{evaluation_failed} 项需要注意。",
            }
        )
    if workflow_seen:
        steps.append(
            {
                "label": "检查工作流运行状态",
                "kind": "workflow",
                "status": "error" if evaluation_failed else "done",
                "detail": "已记录 workflow validation / dry-run 结果。",
            }
        )
    if reviews:
        steps.append(
            {
                "label": "处理 review 结果",
                "kind": "review",
                "status": "error" if any(item != "Review passed" for item in reviews) else "done",
                "detail": _join_preview(_dedupe(reviews)),
            }
        )
    if tool_results:
        tool_status = (
            "error"
            if any(_tool_status(item) == "error" for item in tool_results)
            else "done"
        )
        steps.append(
            {
                "label": "执行平台和工作区工具",
                "kind": "tool",
                "status": tool_status,
                "detail": _tool_detail(tool_results),
            }
        )
    return steps


def _task_detail(state: TaskState, result: TaskResult | None) -> str:
    if state == TaskState.SUCCEEDED:
        attempts = len(result.attempts) if result is not None else 0
        if attempts > 1:
            return "重试或修复后已完成。"
        return "已完成。"
    if state == TaskState.SKIPPED:
        return "前置步骤未完成，因此跳过。"
    if state == TaskState.PENDING:
        return "编排结束前尚未执行。"
    if state == TaskState.ARTIFACT_MISSING:
        return "预期产物未找到。"
    if state == TaskState.EVALUATION_FAILED:
        return "验证检查未通过。"
    return "执行未成功完成，需要检查运行环境或配置。"


def _overall_process_status(
    states: Iterable[TaskState],
    run_context: OrchestratorRunContext,
    tool_results: Sequence[Any],
) -> str:
    all_states = list(states) or [result.final_state for result in run_context.results.values()]
    has_tool_error = any(_tool_status(item) == "error" for item in tool_results)
    if not all_states:
        return "error" if has_tool_error else "done"
    failed_states = {
        TaskState.FAILED,
        TaskState.ARTIFACT_MISSING,
        TaskState.EVALUATION_FAILED,
    }
    has_success = any(state == TaskState.SUCCEEDED for state in all_states)
    has_pending_or_skipped = any(
        state in {TaskState.PENDING, TaskState.SKIPPED} for state in all_states
    )
    has_failed = any(state in failed_states for state in all_states) or has_tool_error
    if has_failed and not has_success:
        return "error"
    if has_failed or has_pending_or_skipped:
        return "partial"
    return "done"


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
        states[task.task_id] = result.final_state if result is not None else TaskState.PENDING
    return states


def _state_to_step_status(state: TaskState) -> str:
    if state == TaskState.SUCCEEDED:
        return "done"
    if state in {TaskState.PENDING, TaskState.SKIPPED}:
        return "skipped"
    return "error"


def _task_kind(task: SubTask) -> str:
    if task.task_type == "review":
        return "review"
    if task.task_type == "repair":
        return "repair"
    return "dispatch"


def _final_agent_id(task: SubTask, result: TaskResult | None) -> str | None:
    if result is not None and result.attempts:
        return result.attempts[-1].agent_id
    return task.agent_id


def _tool_status(item: Any) -> str:
    status = getattr(item, "status", None)
    return str(status or "").lower()


def _tool_name(item: Any) -> str:
    name = getattr(item, "tool_name", None)
    if not isinstance(name, str) or not name:
        name = getattr(item, "name", None)
    return str(name or "tool")


def _tool_detail(tool_results: Sequence[Any]) -> str:
    names = [_friendly_tool_name(_tool_name(item)) for item in tool_results[:6]]
    error_count = sum(1 for item in tool_results if _tool_status(item) == "error")
    prefix = _join_preview(_dedupe(names))
    if error_count:
        return f"{prefix}；{error_count} 个工具结果需要注意。"
    return f"{prefix}。"


def _friendly_tool_name(name: str) -> str:
    return name.replace("_", " ").strip() or "tool"


def _review_label(outcome: str) -> str:
    normalized = outcome.strip().lower()
    if normalized == "passed":
        return "Review passed"
    return "Review requested changes"


def _title(messages: Sequence[ChatMessage]) -> str:
    return "思考与执行"


def _status_summary(status: str, messages: Sequence[ChatMessage]) -> str:
    zh = _prefers_chinese(_latest_user_request(messages))
    if zh:
        return {
            "done": "过程已完成，下面是最终回答。",
            "partial": "过程部分完成，下面的回答包含需要注意的事项。",
            "error": "过程未能成功完成，下面说明可见问题。",
            "running": "过程仍在进行。",
        }.get(status, "过程已整理。")
    return {
        "done": "Process complete. The final answer follows.",
        "partial": "Process partially complete. The final answer includes items needing attention.",
        "error": (
            "Process did not complete successfully. The final answer explains the visible issue."
        ),
        "running": "Process is still running.",
    }.get(status, "Process summarized.")


def _latest_user_request(messages: Sequence[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _prefers_chinese(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _process_status(value: object) -> str:
    if value in {"running", "done", "partial", "error"}:
        return str(value)
    return "done"


def _step_status(value: object) -> str:
    if value in {"done", "running", "error", "skipped"}:
        return str(value)
    return "done"


def _step_kind(value: object) -> str:
    if isinstance(value, str) and value in KIND_VALUES:
        return value
    return "summary"


def _safe_metadata(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or key in {"raw", "prompt", "stderr", "call_id"}:
            continue
        if isinstance(item, str):
            clean[key] = _clean_text(item, 120)
        elif isinstance(item, bool | int | float) or item is None:
            clean[key] = item
    return clean


def _clean_optional(value: object, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _clean_text(value, limit)


def _clean_text(value: object, limit: int) -> str:
    text = " ".join(str(value).replace("```", " ").split())
    if not text:
        return ""
    if _looks_like_raw_error(text):
        text = "运行环境或配置需要检查。"
    for pattern in FORBIDDEN_PROCESS_PATTERNS:
        text = re.sub(re.escape(pattern), "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:call[_-]|orch\.)[\w.-]+", "", text)
    text = re.sub(r"\btask[-_][A-Za-z0-9_.-]+", "任务", text)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _clean_step_id(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().lower()
    text = re.sub(r"\bcall[_-][a-z0-9_.-]+", "", text)
    text = re.sub(r"\borch\.[a-z0-9_.-]+", "", text)
    text = re.sub(r"[^a-z0-9_.-]+", "-", text).strip("-")
    if not text:
        return None
    return text[:64]


def _looks_like_raw_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "traceback",
            "permission denied",
            "[errno",
            "stack trace",
            "stderr",
        )
    )


def _join_preview(items: Sequence[str], *, limit: int = 6) -> str:
    visible = [item for item in items if item][:limit]
    suffix = "" if len(items) <= limit else f" 等 {len(items)} 项"
    return ", ".join(visible) + suffix


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        values.append(item)
    return values
