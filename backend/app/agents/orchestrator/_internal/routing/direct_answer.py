"""Direct-answer path for AgentHub Orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator._internal.routing.evidence import (
    ORCHESTRATOR_EVIDENCE_HEADER,
    evidence_answer_text,
    is_evidence_followup_request,
)
from app.agents.orchestrator._internal.streams import (
    attach_agent_id,
    remap_block_index,
    remap_tool_call_id,
)
from app.agents.orchestrator.availability import scoped_runnable_agent_ids
from app.agents.types import ChatMessage, StreamChunk

DIRECT_ANSWER_SYSTEM_PROMPT = """You are AgentHub's Orchestrator.
Answer simple questions about your identity, configured model backend, capabilities,
and coordination role directly. Do not create a task plan for these answers.
For implementation or artifact-building requests, the backend will use the planner
and dispatch specialist agents instead.
In direct-answer mode, never say that you will delegate, assign, invoke, call,
hand off, or route work to another agent. Direct answers do not dispatch agents.
When the user asks about a previous, latest, or just-finished Orchestrator task, use
the injected structured memory. Only say you cannot confirm if no structured memory
or run record exists in the current conversation.
"""

META_QUESTION_MARKERS = (
    "\u4f60\u597d",
    "\u60a8\u597d",
    "\u4f60\u662f\u8c01",
    "\u4f60\u662f\u4ec0\u4e48",
    "\u4f60\u662f\u4ec0\u4e48\u6a21\u578b",
    "\u4f60\u7528\u4ec0\u4e48\u6a21\u578b",
    "\u4ec0\u4e48\u6a21\u578b",
    "\u54ea\u4e2a\u6a21\u578b",
    "\u4f60\u6709\u4ec0\u4e48\u80fd\u529b",
    "\u4f60\u80fd\u505a\u4ec0\u4e48",
    "\u4f60\u7684\u80fd\u529b",
    "\u4f60\u7684\u804c\u8d23",
    "\u4ecb\u7ecd\u4e00\u4e0b",
    "\u81ea\u6211\u4ecb\u7ecd",
    "\u4f60\u4e4b\u524d\u6709\u4ec0\u4e48\u7f16\u7a0b\u4efb\u52a1",
    "\u4e4b\u524d\u6709\u4ec0\u4e48\u7f16\u7a0b\u4efb\u52a1",
    "\u4e4b\u524d\u6709\u4ec0\u4e48\u4efb\u52a1",
    "\u7f16\u7a0b\u4efb\u52a1\u5417",
    "\u6267\u884c\u5b8c\u6210\u4e86\u5417",
    "\u6267\u884c\u5b8c\u6210\u6ca1",
    "\u5b8c\u6210\u4e86\u5417",
    "\u5b8c\u6210\u6ca1",
    "\u521a\u521a\u7684\u4efb\u52a1",
    "\u521a\u624d\u7684\u4efb\u52a1",
    "\u4e0a\u4e00\u4e2a\u4efb\u52a1",
    "\u4e0a\u6b21\u7684\u4efb\u52a1",
    "\u4e4b\u524d\u90a3\u4e2a\u4efb\u52a1",
    "\u6211\u6307\u521a\u521a",
    "hello",
    "hi",
    "hey",
    "who are you",
    "what model",
    "which model",
    "what runtime",
    "what can you do",
    "your capabilities",
    "introduce yourself",
    "did it finish",
    "is it done",
    "previous task",
    "last task",
)

RECENT_TASK_STATUS_MARKERS = (
    "\u6267\u884c\u5b8c\u6210",
    "\u5b8c\u6210\u4e86\u5417",
    "\u5b8c\u6210\u6ca1",
    "\u505a\u5b8c",
    "\u521a\u521a\u7684\u4efb\u52a1",
    "\u521a\u624d\u7684\u4efb\u52a1",
    "\u4e0a\u4e00\u4e2a\u4efb\u52a1",
    "\u4e0a\u6b21\u7684\u4efb\u52a1",
    "\u4e4b\u524d\u90a3\u4e2a",
    "\u6211\u6307\u521a\u521a",
    "\u90a3\u4e2a\u4efb\u52a1",
    "did it finish",
    "is it done",
    "previous task",
    "last task",
)

ORCHESTRATOR_MEMORY_PREFIX = "Previous Orchestrator structured memory:"


def should_direct_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    *,
    latest_user_request: Callable[[list[ChatMessage]], str],
    agent_id_list: Callable[[object], list[str]],
    explicit_agent_mentions: Callable[[list[str], str], list[str]],
    strip_orchestrator_mention: Callable[[str], str],
    has_task_intent: Callable[[str], bool],
) -> bool:
    if config.get("tasks") is not None:
        return False
    user_request = latest_user_request(messages)
    scoped_ids = scoped_runnable_agent_ids(config)
    agent_ids = (
        scoped_ids
        if scoped_ids is not None
        else agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))
    )
    if explicit_agent_mentions(agent_ids, user_request):
        return False
    normalized = strip_orchestrator_mention(user_request).lower()
    if is_evidence_followup_request(normalized):
        return True
    if has_task_intent(normalized):
        return False
    if _is_simple_greeting(normalized):
        return True
    return any(marker in normalized for marker in META_QUESTION_MARKERS)


def _is_simple_greeting(text: str) -> bool:
    compact = text.strip().strip("!！?？。,.， ")
    return compact in {
        "\u4f60\u597d",
        "\u60a8\u597d",
        "hello",
        "hi",
        "hey",
    }


async def run_direct_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    next_block_index: int,
    *,
    latest_user_request: Callable[[list[ChatMessage]], str],
    workspace_path: Path | None = None,
) -> AsyncIterator[tuple[StreamChunk, int, bool]]:
    evidence_text = await evidence_answer_text(
        config,
        latest_user_request(messages),
        workspace_path,
    )
    if evidence_text is not None:
        for chunk in _text_block(next_block_index, evidence_text):
            yield chunk, next_block_index + 1, False
        return

    status_text = await _recent_task_status_answer(
        config,
        latest_user_request(messages),
    )
    if status_text is not None:
        for chunk in _text_block(next_block_index, status_text):
            yield chunk, next_block_index + 1, False
        return

    try:
        gateway = _answer_gateway(config, system_prompt)
        answer_config = _answer_config(config)
    except ValueError as exc:
        yield StreamChunk(
            event_type="error",
            error_code=_error_code(exc),
            error=str(exc),
            agent_id="orchestrator",
        ), next_block_index, True
        return

    index_map: dict[int, int] = {}
    open_block_index: int | None = None

    try:
        async for chunk in gateway.stream(
            _answer_messages(messages, latest_user_request=latest_user_request),
            system_prompt=_answer_system_prompt(config, system_prompt),
            config=answer_config,
        ):
            if chunk.event_type in {"start", "done"}:
                continue
            if chunk.event_type == "error":
                if open_block_index is not None:
                    yield StreamChunk(
                        event_type="block_end",
                        block_index=open_block_index,
                        agent_id="orchestrator",
                    ), next_block_index, False
                    open_block_index = None
                yield attach_agent_id(chunk, "orchestrator"), next_block_index, True
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                remapped = remap_tool_call_id(chunk, "direct-answer")
                yield attach_agent_id(remapped, "orchestrator"), next_block_index, False
                continue
            if chunk.event_type == "heartbeat":
                yield attach_agent_id(chunk, "orchestrator"), next_block_index, False
                continue
            if chunk.event_type not in {"block_start", "delta", "block_end"}:
                continue
            remapped, next_block_index = remap_block_index(
                chunk,
                index_map,
                next_block_index,
            )
            if remapped.event_type == "block_start":
                open_block_index = remapped.block_index
            elif remapped.event_type == "block_end":
                open_block_index = None
            yield attach_agent_id(remapped, "orchestrator"), next_block_index, False
    except Exception as exc:
        if open_block_index is not None:
            yield StreamChunk(
                event_type="block_end",
                block_index=open_block_index,
                agent_id="orchestrator",
            ), next_block_index, False
        yield StreamChunk(
            event_type="error",
            error_code="upstream_error",
            error=str(exc),
            agent_id="orchestrator",
        ), next_block_index, True


def _answer_gateway(config: Mapping[str, Any], system_prompt: str | None) -> Any:
    gateway = config.get("answer_gateway")
    if gateway is not None:
        return gateway

    backend = config.get("answer_model_backend", config.get("model_backend", "claude"))
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("invalid_answer_config: answer model backend must be a string")
    return ModelGateway(
        backend,
        default_config=_answer_config(config),
        agent_id="orchestrator-answer",
        system_prompt=_answer_system_prompt(config, system_prompt),
    )


def _answer_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw_config = config.get("orchestrator_answer_config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ValueError(
            "invalid_answer_config: orchestrator_answer_config must be an object"
        )

    answer_config: dict[str, Any] = {
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    answer_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in answer_config:
            answer_config[key] = config[key]
    return answer_config


def _answer_system_prompt(config: Mapping[str, Any], system_prompt: str | None) -> str:
    backend = config.get("answer_model_backend", config.get("model_backend", "claude"))
    backend_name = backend if isinstance(backend, str) and backend else "claude"
    prompt = (
        f"{DIRECT_ANSWER_SYSTEM_PROMPT}\n"
        f"Configured answer backend: {backend_name}.\n"
        "If asked what model you are, answer as AgentHub Orchestrator and mention "
        "that your direct answers use the configured ModelGateway backend."
    )
    if system_prompt:
        return f"{system_prompt}\n\n{prompt}"
    return prompt


def _answer_messages(
    messages: list[ChatMessage],
    *,
    latest_user_request: Callable[[list[ChatMessage]], str],
) -> list[ChatMessage]:
    user_request = latest_user_request(messages)
    memory_messages = [
        message
        for message in messages
        if message.role == "system"
        and message.content.strip().startswith(
            (ORCHESTRATOR_MEMORY_PREFIX, ORCHESTRATOR_EVIDENCE_HEADER)
        )
    ]
    return [
        *memory_messages,
        ChatMessage(
            role="user",
            content=(
                "Answer this user message directly as AgentHub Orchestrator. "
                "Do not create or describe a task plan. Do not claim that another "
                "agent will be delegated, assigned, invoked, called, or handed "
                "the work. If the user asks about a previous or just-finished task, "
                "answer from the structured memory above and mention concrete status, "
                "agents, artifacts, or errors when present.\n\n"
                f"User message:\n{user_request}"
            ),
        )
    ]


async def _recent_task_status_answer(
    config: Mapping[str, Any],
    user_request: str,
) -> str | None:
    if not _is_recent_task_status_request(user_request):
        return None
    db = config.get("orchestrator_db_session")
    conversation_id = config.get("conversation_id")
    if db is None or conversation_id is None:
        return "我现在没有拿到当前会话的任务记录连接，所以无法确认刚刚任务的状态。"
    try:
        from app.services.orchestrator_memory import (  # noqa: PLC0415
            get_orchestrator_run_detail,
            list_orchestrator_runs,
        )

        runs = await list_orchestrator_runs(db, conversation_id, limit=5)
        if not runs:
            return "我查了当前会话的 Orchestrator 运行记录，还没有找到已经登记的任务。"
        run = runs[0]
        detail = await get_orchestrator_run_detail(db, conversation_id, run.id)
        if detail is None:
            return "我找到了最近的 Orchestrator 任务记录，但读取详情失败，请稍后重试。"
        run, tasks, attempts, _events = detail
        return _format_recent_task_status(run, tasks, attempts)
    except Exception:  # noqa: BLE001
        return "我读取当前会话的 Orchestrator 任务记录时失败了，请稍后重试。"


def _is_recent_task_status_request(text: str) -> bool:
    normalized = text.lower()
    return any(marker in normalized for marker in RECENT_TASK_STATUS_MARKERS)


def _format_recent_task_status(run: Any, tasks: list[Any], attempts: list[Any]) -> str:
    status = _status_label(getattr(run, "status", "unknown"))
    request = _single_line(getattr(run, "user_request", ""), 120)
    lines = [f"最近一次 Orchestrator 任务状态：{status}。"]
    if request:
        lines.append(f"任务请求：{request}")

    attempts_by_task: dict[str, list[Any]] = {}
    for attempt in attempts:
        task_id = getattr(attempt, "task_id", "")
        attempts_by_task.setdefault(task_id, []).append(attempt)

    for task in tasks[:6]:
        task_id = getattr(task, "task_id", "")
        task_attempts = attempts_by_task.get(task_id, [])
        final_attempt = task_attempts[-1] if task_attempts else None
        agent_id = (
            getattr(final_attempt, "agent_id", None)
            or getattr(task, "agent_id", "")
            or "unknown"
        )
        task_status = _status_label(getattr(task, "final_state", "unknown"))
        title = _single_line(getattr(task, "title", "") or task_id, 80)
        line = f"- {task_status}: @{agent_id} - {title}"
        artifacts = _artifact_paths(task_attempts)
        if artifacts:
            line += f"；产物：{', '.join(artifacts[:5])}"
        error = getattr(final_attempt, "error", None) if final_attempt else None
        if isinstance(error, str) and error.strip():
            line += f"；错误：{_single_line(error, 120)}"
        lines.append(line)

    summary = _single_line(getattr(run, "final_summary", ""), 180)
    if summary:
        lines.append(f"总结：{summary}")
    return "\n".join(lines)


def _artifact_paths(attempts: list[Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for attempt in attempts:
        raw_paths = getattr(attempt, "artifact_paths", None)
        if not isinstance(raw_paths, list):
            continue
        for path in raw_paths:
            if not isinstance(path, str) or not path.strip() or path in seen:
                continue
            seen.add(path)
            paths.append(path)
    return paths


def _status_label(status: object) -> str:
    value = str(status or "unknown").lower()
    return {
        "done": "已完成",
        "succeeded": "已完成",
        "passed": "已完成",
        "error": "失败",
        "failed": "失败",
        "running": "执行中",
        "pending": "等待中",
        "skipped": "已跳过",
        "artifact_missing": "产物缺失",
        "evaluation_failed": "验收失败",
    }.get(value, value)


def _single_line(text: object, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(0, limit - 1)].rstrip() + "…"


def _text_block(block_index: int, text: str) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
            agent_id="orchestrator",
        ),
        StreamChunk(
            event_type="delta",
            block_index=block_index,
            text_delta=text,
            agent_id="orchestrator",
        ),
        StreamChunk(
            event_type="block_end",
            block_index=block_index,
            agent_id="orchestrator",
        ),
    )


def _error_code(exc: ValueError) -> str:
    message = str(exc)
    if ":" in message:
        return message.split(":", 1)[0]
    return "invalid_request"
