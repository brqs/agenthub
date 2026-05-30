"""Orchestrator injection-based sub-agent dispatch."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Mapping
from pathlib import Path
from typing import Any, cast

from app.agents.base import BaseAgentAdapter
from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator_planner import llm_planning_enabled, plan_task_payload
from app.agents.orchestrator_platform_facts import (
    platform_fact_intent,
    platform_fact_text,
)
from app.agents.orchestrator_react import react_enabled, run_react_loop
from app.agents.orchestrator_tool_loop import (
    run_orchestrator_tool_loop,
    tool_calling_enabled,
)
from app.agents.orchestrator_types import (
    DEFAULT_MAX_TASK_ATTEMPTS,
    DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS,
    DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    MAX_TASK_ATTEMPTS_LIMIT,
    AdapterFactory,
    OrchestratorMemoryWriter,
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

SENSITIVE_ARTIFACT_PARTS = {".env", "secrets", ".ssh", ".agenthub"}
ARTIFACT_PATH_KEYS = {
    "path",
    "file_path",
    "filepath",
    "filename",
    "file",
    "target_path",
    "output_path",
}
ARTIFACT_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.\-/\\])"
    r"([A-Za-z0-9_.\-/\\]+"
    r"\.(?:html|css|js|jsx|ts|tsx|py|md|json|txt|yml|yaml|toml|xml|svg|png|jpg|jpeg|gif|webp))"
)

DIRECT_ANSWER_SYSTEM_PROMPT = """You are AgentHub's Orchestrator.
Answer simple questions about your identity, configured model backend, capabilities,
and coordination role directly. Do not create a task plan for these answers.
For implementation or artifact-building requests, the backend will use the planner
and dispatch specialist agents instead.
"""

META_QUESTION_MARKERS = (
    "你是谁",
    "你是什么",
    "什么模型",
    "哪个模型",
    "什么 runtime",
    "什么runtime",
    "能做什么",
    "可以做什么",
    "介绍一下",
    "自我介绍",
    "你的能力",
    "你的职责",
    "who are you",
    "what model",
    "which model",
    "what runtime",
    "what can you do",
    "your capabilities",
    "introduce yourself",
)

TASK_INTENT_MARKERS = (
    "生成",
    "创建",
    "写一个",
    "写入",
    "实现",
    "构建",
    "修改",
    "修复",
    "部署",
    "复核",
    "安排",
    "协调",
    "调用",
    "分别",
    "让 ",
    "让@",
    "build",
    "create",
    "generate",
    "write",
    "implement",
    "fix",
    "deploy",
    "review",
    "coordinate",
    "ask ",
)
PLANNER_PROTOCOL_ERROR_MARKERS = (
    "invalid_json",
    "empty_planner_output",
    "planner failed",
)
PORT_SERVICE_TASK_MARKERS = (
    "preview",
    "deploy",
    "port",
    "server",
    "service",
    "808",
    "预览",
    "部署",
    "端口",
    "服务",
)
ARTIFACT_TASK_MARKERS = (
    "create",
    "generate",
    "write",
    "implement",
    "build",
    "file",
    "artifact",
    "html",
    "创建",
    "生成",
    "编写",
    "实现",
    "文件",
    "产物",
)


class PlannerResolutionError(ValueError):
    """Raised when LLM planner output cannot be used as a task plan."""


class OrchestratorAdapter(BaseAgentAdapter):
    """Master agent that coordinates multiple sub-agents in group chat."""

    provider = "builtin"

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id=self.agent_id)

        merged_config = self.merged_config(config)
        next_block_index = 0
        platform_fact = await platform_fact_intent(
            merged_config,
            messages,
            latest_user_request=_latest_user_request,
            agent_id_list=_agent_id_list,
            explicit_agent_mentions=_explicit_agent_mentions,
            has_task_intent=_has_task_intent,
            error_reason=_error_reason,
        )
        if platform_fact:
            for chunk in _text_block(
                next_block_index,
                platform_fact_text(merged_config, platform_fact),
            ):
                yield chunk
            next_block_index += 1
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=next_block_index,
            )
            return
        if _should_direct_answer(merged_config, messages):
            async for chunk, updated_block_index, failed in _run_direct_answer(
                merged_config,
                messages,
                self.effective_system_prompt(system_prompt),
                next_block_index,
            ):
                next_block_index = updated_block_index
                yield chunk
                if failed:
                    return
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=next_block_index,
            )
            return

        if merged_config.get("tasks") is None and tool_calling_enabled(merged_config):
            run_context = OrchestratorRunContext()
            try:
                async for chunk, updated_block_index in run_orchestrator_tool_loop(
                    merged_config,
                    messages,
                    next_block_index,
                    workspace_path,
                    tool_specs,
                    run_context=run_context,
                    run_task=_run_task,
                    text_block_with_next=_text_block_with_next,
                    latest_user_request=_latest_user_request,
                    positive_int_config=_positive_int_config,
                    format_task_result_context=_format_task_result_context,
                ):
                    next_block_index = updated_block_index
                    yield chunk
                    if chunk.event_type == "error":
                        return
            except ValueError as exc:
                yield StreamChunk(
                    event_type="error",
                    error_code=_error_code(exc),
                    error=str(exc),
                    agent_id=self.agent_id,
                )
                return
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=next_block_index,
            )
            return

        try:
            tasks = await _resolve_tasks(
                merged_config,
                messages,
                self.effective_system_prompt(system_prompt),
            )
        except PlannerResolutionError as exc:
            if _should_direct_answer_after_planner_error(merged_config, exc):
                async for chunk, updated_block_index, failed in _run_direct_answer(
                    merged_config,
                    messages,
                    self.effective_system_prompt(system_prompt),
                    next_block_index,
                ):
                    next_block_index = updated_block_index
                    yield chunk
                    if failed:
                        return
                yield StreamChunk(
                    event_type="done",
                    agent_id=self.agent_id,
                    total_blocks=next_block_index,
                )
                return
            if _has_fallback(merged_config):
                async for chunk, updated_block_index in _run_fallback(
                    merged_config,
                    messages,
                    next_block_index,
                    workspace_path,
                    tool_specs,
                ):
                    next_block_index = updated_block_index
                    yield chunk
                for chunk in _text_block(next_block_index, _fallback_summary_text()):
                    yield chunk
                next_block_index += 1
                yield StreamChunk(
                    event_type="done",
                    agent_id=self.agent_id,
                    total_blocks=next_block_index,
                )
                return
            yield StreamChunk(
                event_type="error",
                error_code=_error_code(exc),
                error=str(exc),
                agent_id=self.agent_id,
            )
            return
        except ValueError as exc:
            if _has_fallback(merged_config):
                async for chunk, updated_block_index in _run_fallback(
                    merged_config,
                    messages,
                    next_block_index,
                    workspace_path,
                    tool_specs,
                ):
                    next_block_index = updated_block_index
                    yield chunk
                for chunk in _text_block(next_block_index, _fallback_summary_text()):
                    yield chunk
                next_block_index += 1
                yield StreamChunk(
                    event_type="done",
                    agent_id=self.agent_id,
                    total_blocks=next_block_index,
                )
                return
            yield StreamChunk(
                event_type="error",
                error_code=_error_code(exc),
                error=str(exc),
                agent_id=self.agent_id,
            )
            return

        try:
            _ensure_adapter_source(merged_config)
        except ValueError as exc:
            yield StreamChunk(
                event_type="error",
                error_code=_error_code(exc),
                error=str(exc),
                agent_id=self.agent_id,
            )
            return

        run_context = OrchestratorRunContext()
        await _memory_start_run_for_messages(merged_config, run_context, tasks, messages)
        for chunk in _text_block(next_block_index, _planning_text(tasks)):
            yield chunk
        next_block_index += 1

        if react_enabled(merged_config):
            async for chunk, updated_block_index in run_react_loop(
                merged_config,
                tasks,
                messages,
                next_block_index,
                workspace_path,
                tool_specs,
                run_context=run_context,
                run_task=_run_task,
                text_block_with_next=_text_block_with_next,
                summary_text=_summary_text,
                format_task_result_context=_format_task_result_context,
                latest_user_request=_latest_user_request,
                positive_int_config=_positive_int_config,
                agent_id_list=_agent_id_list,
                error_reason=_error_reason,
            ):
                next_block_index = updated_block_index
                yield chunk
        else:
            async for chunk, updated_block_index in _run_static_tasks(
                merged_config,
                tasks,
                messages,
                next_block_index,
                workspace_path,
                tool_specs,
                run_context,
            ):
                next_block_index = updated_block_index
                yield chunk
        yield StreamChunk(
            event_type="done", agent_id=self.agent_id, total_blocks=next_block_index
        )


async def _resolve_tasks(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
) -> list[SubTask]:
    raw_tasks = config.get("tasks")
    if raw_tasks is None:
        direct_tasks = _direct_tasks_from_request(config, messages)
        if direct_tasks:
            return direct_tasks
        if llm_planning_enabled(config):
            try:
                return await _plan_tasks_with_model(config, messages, system_prompt)
            except ValueError as exc:
                if _planner_fallback_to_template(config):
                    return _derive_tasks(config, messages)
                raise PlannerResolutionError(str(exc)) from exc
        return _derive_tasks(config, messages)

    return _parse_task_list(raw_tasks)


def _parse_task_list(raw_tasks: object) -> list[SubTask]:
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("missing_task_plan: config.tasks must be a non-empty list")

    tasks: list[SubTask] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, Mapping):
            raise ValueError("invalid_task_plan: each task must be an object")
        tasks.append(SubTask.from_mapping(cast(Mapping[str, Any], raw_task)))
    _ensure_unique_task_ids(tasks)
    return sorted(tasks, key=lambda task: task.priority)


async def _plan_tasks_with_model(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
) -> list[SubTask]:
    planner_output = await plan_task_payload(
        config,
        messages,
        system_prompt,
        _latest_user_request(messages),
    )
    tasks = _tasks_from_planner_payload(planner_output.payload)
    _validate_planned_tasks(tasks, planner_output.allowed_agent_ids)
    return _remove_port_service_tasks(tasks)


def _tasks_from_planner_payload(payload: Any) -> list[SubTask]:
    raw_tasks = payload.get("tasks") if isinstance(payload, Mapping) else payload
    return _parse_task_list(raw_tasks)


def _validate_planned_tasks(tasks: list[SubTask], allowed_agent_ids: set[str]) -> None:
    task_ids = {task.task_id for task in tasks}
    for task in tasks:
        if task.agent_id not in allowed_agent_ids:
            raise ValueError(
                f"invalid_task_plan: unknown agent_id {task.agent_id!r}"
            )
        missing_deps = [dep for dep in task.depends_on if dep not in task_ids]
        if missing_deps:
            raise ValueError(
                f"invalid_task_plan: unknown depends_on task_id {missing_deps[0]!r}"
            )


def _remove_port_service_tasks(tasks: list[SubTask]) -> list[SubTask]:
    depended_on = {dependency for task in tasks for dependency in task.depends_on}
    kept = [
        task
        for task in tasks
        if task.task_id in depended_on or not _is_port_service_task(task)
    ]
    return kept or tasks


def _is_port_service_task(task: SubTask) -> bool:
    text = f"{task.title}\n{task.instruction}".lower()
    if not any(marker in text for marker in PORT_SERVICE_TASK_MARKERS):
        return False
    return not any(marker in text for marker in ARTIFACT_TASK_MARKERS)


def _direct_tasks_from_request(
    config: Mapping[str, Any], messages: list[ChatMessage]
) -> list[SubTask]:
    agent_ids = _agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
    if not agent_ids:
        return []
    return _derive_direct_agent_tasks(agent_ids, _latest_user_request(messages))


def _planner_fallback_to_template(config: Mapping[str, Any]) -> bool:
    return config.get("planner_fallback_to_template") is True


def _direct_answer_on_planner_failure(config: Mapping[str, Any]) -> bool:
    return config.get("direct_answer_on_planner_failure") is True


def _should_direct_answer_after_planner_error(
    config: Mapping[str, Any],
    exc: PlannerResolutionError,
) -> bool:
    if not _direct_answer_on_planner_failure(config):
        return False
    message = str(exc)
    return any(marker in message for marker in PLANNER_PROTOCOL_ERROR_MARKERS)


def _should_direct_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> bool:
    if config.get("tasks") is not None:
        return False
    user_request = _latest_user_request(messages)
    agent_ids = _agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
    if _explicit_agent_mentions(agent_ids, user_request):
        return False
    normalized = _strip_orchestrator_mention(user_request).lower()
    if _has_task_intent(normalized):
        return False
    return any(marker in normalized for marker in META_QUESTION_MARKERS)


def _strip_orchestrator_mention(text: str) -> str:
    return text.replace("@orchestrator", "").replace("＠orchestrator", "").strip()


def _has_task_intent(text: str) -> bool:
    return any(marker in text for marker in TASK_INTENT_MARKERS)


def _derive_tasks(config: Mapping[str, Any], messages: list[ChatMessage]) -> list[SubTask]:
    agent_ids = _agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
    if not agent_ids:
        raise ValueError(
            "missing_task_plan: config.tasks or config.managed_agent_ids is required"
        )

    user_request = _latest_user_request(messages)
    direct_tasks = _derive_direct_agent_tasks(agent_ids, user_request)
    if direct_tasks:
        return direct_tasks

    titles = (
        "Analyze request",
        "Produce solution",
        "Review and refine",
    )
    instructions = (
        "Analyze the user's request and propose the implementation approach."
        f"\n\nRequest:\n{user_request}",
        "Implement or draft the requested result. Include concrete artifacts when useful."
        f"\n\nRequest:\n{user_request}",
        "Review the result for gaps, risks, and next steps. Keep the answer concise."
        f"\n\nRequest:\n{user_request}",
    )

    tasks: list[SubTask] = []
    for index, agent_id in enumerate(agent_ids[:3]):
        title = titles[index] if index < len(titles) else f"Subtask {index + 1}"
        instruction = instructions[index] if index < len(instructions) else user_request
        tasks.append(
            SubTask(
                task_id=f"auto-{index + 1}",
                agent_id=agent_id,
                title=title,
                instruction=instruction,
                priority=index,
            )
        )
    return tasks


def _derive_direct_agent_tasks(agent_ids: list[str], user_request: str) -> list[SubTask]:
    targets = _explicit_agent_mentions(agent_ids, user_request)
    if len(targets) < 2:
        return []

    message = _extract_quoted_message(user_request) or user_request
    return [
        SubTask(
            task_id=f"direct-{index + 1}",
            agent_id=agent_id,
            title="Direct request",
            instruction=_direct_agent_instruction(message),
            priority=index,
            include_history=False,
        )
        for index, agent_id in enumerate(targets)
    ]


def _explicit_agent_mentions(agent_ids: list[str], user_request: str) -> list[str]:
    normalized = user_request.lower()
    available = set(agent_ids)
    positions: list[tuple[int, int, str]] = []

    for order, agent_id in enumerate(agent_ids):
        if agent_id not in available:
            continue
        position = _first_alias_position(normalized, _agent_aliases(agent_id))
        if position is not None:
            positions.append((position, order, agent_id))

    positions.sort()
    return [agent_id for _, _, agent_id in positions]


def _agent_aliases(agent_id: str) -> tuple[str, ...]:
    if agent_id == "claude-code":
        return ("@claude-code", "claude-code", "claude code", "claudecode")
    if agent_id == "codex-helper":
        return ("@codex-helper", "codex-helper", "codex helper", "codex")
    if agent_id == "opencode-helper":
        return (
            "@opencode-helper",
            "opencode-helper",
            "opencode helper",
            "open code",
            "opencode",
        )
    if agent_id == "web-designer":
        return ("@web-designer", "web-designer", "web designer")
    return (f"@{agent_id}", agent_id)


def _first_alias_position(text: str, aliases: tuple[str, ...]) -> int | None:
    positions = [text.find(alias) for alias in aliases]
    matches = [position for position in positions if position >= 0]
    return min(matches) if matches else None


def _extract_quoted_message(user_request: str) -> str | None:
    quote_pairs = (("“", "”"), ('"', '"'), ("'", "'"))
    for open_quote, close_quote in quote_pairs:
        start = user_request.find(open_quote)
        if start < 0:
            continue
        end = user_request.find(close_quote, start + 1)
        if end <= start:
            continue
        quoted = user_request[start + 1 : end].strip()
        if quoted:
            return quoted
    return None


def _direct_agent_instruction(message: str) -> str:
    return (
        "You are receiving a direct request from AgentHub Orchestrator.\n"
        "Answer the message yourself only. Do not contact, invoke, or simulate "
        "other agents, CLIs, or APIs.\n"
        "If the message asks what model or runtime you are, answer from your own "
        "runtime identity.\n\n"
        f"Message:\n{message}\n\n"
        "Keep the response concise."
    )


def _agent_id_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        agent_id = item.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        result.append(agent_id)
    return result


def _latest_user_request(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return "Handle the user's request."


def _ensure_unique_task_ids(tasks: list[SubTask]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.task_id in seen:
            raise ValueError(f"invalid_task_plan: duplicate task_id {task.task_id!r}")
        seen.add(task.task_id)


def _ensure_adapter_source(config: Mapping[str, Any]) -> None:
    if isinstance(config.get("sub_adapters"), Mapping):
        return
    if callable(config.get("adapter_factory")):
        return
    raise ValueError(
        "missing_sub_adapters: config.sub_adapters or config.adapter_factory is required"
    )


def _has_fallback(config: Mapping[str, Any]) -> bool:
    if isinstance(config.get("fallback_adapter"), BaseAgentAdapter):
        return True
    if callable(config.get("fallback_adapter_factory")):
        return True
    return False


async def _get_fallback_adapter(config: Mapping[str, Any]) -> BaseAgentAdapter:
    fallback_adapter = config.get("fallback_adapter")
    if isinstance(fallback_adapter, BaseAgentAdapter):
        return fallback_adapter

    factory = config.get("fallback_adapter_factory")
    if callable(factory):
        result = factory()
        adapter = await result if isinstance(result, Awaitable) else result
        if isinstance(adapter, BaseAgentAdapter):
            return adapter
        raise ValueError(
            "fallback_adapter_factory returned a non-BaseAgentAdapter value"
        )

    raise ValueError("no fallback adapter available")


def _get_fallback_agent_id(config: Mapping[str, Any]) -> str:
    agent_id = config.get("fallback_agent_id")
    if isinstance(agent_id, str) and agent_id:
        return agent_id
    return "fallback"


async def _run_fallback(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    fallback_agent_id = _get_fallback_agent_id(config)

    try:
        fallback_adapter = await _get_fallback_adapter(config)
    except Exception as exc:
        for chunk, updated_block_index in _text_block_with_next(
            next_block_index,
            f"@{fallback_agent_id} failed: {exc}",
        ):
            yield chunk, updated_block_index
        return

    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        f"Task plan unavailable; falling back to @{fallback_agent_id}.\n",
    ):
        yield chunk, updated_block_index
    next_block_index += 1

    yield StreamChunk(
        event_type="agent_switch",
        from_agent="orchestrator",
        to_agent=fallback_agent_id,
        task="fallback",
    ), next_block_index

    index_map: dict[int, int] = {}
    open_block_index: int | None = None
    try:
        async for chunk in fallback_adapter.stream(
            messages,
            system_prompt=None,
            config=None,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
        ):
            if chunk.event_type in {"start", "done"}:
                continue
            if chunk.event_type == "error":
                if open_block_index is not None:
                    yield StreamChunk(
                        event_type="block_end", block_index=open_block_index
                    ), next_block_index
                    open_block_index = None
                failure_text = f"@{fallback_agent_id} failed: {_error_reason(chunk)}"
                for failure_chunk in _text_block(next_block_index, failure_text):
                    yield failure_chunk, next_block_index + 1
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                yield _remap_tool_call_id(chunk, "fallback"), next_block_index
                continue
            if chunk.event_type == "heartbeat":
                yield chunk, next_block_index
                continue
            if chunk.event_type not in {"block_start", "delta", "block_end"}:
                continue
            remapped, next_block_index = _remap_block_index(
                chunk,
                index_map,
                next_block_index,
            )
            if remapped.event_type == "block_start":
                open_block_index = remapped.block_index
            elif remapped.event_type == "block_end":
                open_block_index = None
            yield remapped, next_block_index
    except Exception as exc:
        if open_block_index is not None:
            yield StreamChunk(
                event_type="block_end", block_index=open_block_index
            ), next_block_index
            open_block_index = None
        for chunk, updated_block_index in _text_block_with_next(
            next_block_index,
            f"@{fallback_agent_id} failed: {exc}",
        ):
            yield chunk, updated_block_index


async def _run_direct_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    next_block_index: int,
) -> AsyncIterator[tuple[StreamChunk, int, bool]]:
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
            _answer_messages(config, messages),
            system_prompt=_answer_system_prompt(config, system_prompt),
            config=answer_config,
        ):
            if chunk.event_type in {"start", "done"}:
                continue
            if chunk.event_type == "error":
                if open_block_index is not None:
                    yield StreamChunk(
                        event_type="block_end", block_index=open_block_index
                    ), next_block_index, False
                    open_block_index = None
                yield chunk, next_block_index, True
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                yield _remap_tool_call_id(chunk, "direct-answer"), next_block_index, False
                continue
            if chunk.event_type == "heartbeat":
                yield chunk, next_block_index, False
                continue
            if chunk.event_type not in {"block_start", "delta", "block_end"}:
                continue
            remapped, next_block_index = _remap_block_index(
                chunk,
                index_map,
                next_block_index,
            )
            if remapped.event_type == "block_start":
                open_block_index = remapped.block_index
            elif remapped.event_type == "block_end":
                open_block_index = None
            yield remapped, next_block_index, False
    except Exception as exc:
        if open_block_index is not None:
            yield StreamChunk(
                event_type="block_end", block_index=open_block_index
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
        raise ValueError("invalid_answer_config: orchestrator_answer_config must be an object")

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
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[ChatMessage]:
    _ = config
    user_request = _latest_user_request(messages)
    return [
        ChatMessage(
            role="user",
            content=(
                "Answer this user message directly as AgentHub Orchestrator. "
                "Do not create or describe a task plan.\n\n"
                f"User message:\n{user_request}"
            ),
        )
    ]


async def _get_sub_adapter(
    config: Mapping[str, Any], agent_id: str
) -> BaseAgentAdapter:
    sub_adapters = config.get("sub_adapters")
    if isinstance(sub_adapters, Mapping) and agent_id in sub_adapters:
        adapter = sub_adapters[agent_id]
        if isinstance(adapter, BaseAgentAdapter):
            return adapter
        raise ValueError(f"sub_adapters[{agent_id!r}] is not a BaseAgentAdapter")

    factory = config.get("adapter_factory")
    if callable(factory):
        result = cast(AdapterFactory, factory)(agent_id)
        adapter = await result if isinstance(result, Awaitable) else result
        if isinstance(adapter, BaseAgentAdapter):
            return adapter
        raise ValueError("adapter_factory returned a non-BaseAgentAdapter value")

    raise ValueError(f"no injected adapter for agent {agent_id!r}")


def _dependencies_satisfied(
    task: SubTask,
    task_states: Mapping[str, TaskState],
) -> bool:
    return all(
        task_states.get(task_id) == TaskState.SUCCEEDED
        for task_id in task.depends_on
    )


def _agent_switch(task: SubTask, agent_id: str | None = None) -> StreamChunk:
    target_agent_id = agent_id or task.agent_id
    return StreamChunk(
        event_type="agent_switch",
        from_agent="orchestrator",
        to_agent=target_agent_id,
        task=task.title,
    )


def _text_block(
    block_index: int, text: str
) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    return (
        StreamChunk(event_type="block_start", block_index=block_index, block_type="text"),
        StreamChunk(event_type="delta", block_index=block_index, text_delta=text),
        StreamChunk(event_type="block_end", block_index=block_index),
    )


def _text_block_with_next(
    block_index: int,
    text: str,
) -> tuple[tuple[StreamChunk, int], ...]:
    next_block_index = block_index + 1
    return tuple((chunk, next_block_index) for chunk in _text_block(block_index, text))


def _planning_text(tasks: list[SubTask]) -> str:
    lines = [f"Planned {len(tasks)} sub-task(s) via {_plan_source(tasks)}:"]
    for index, task in enumerate(tasks, 1):
        lines.append(f"{index}. @{task.agent_id} - {task.title}")
    return "\n".join(lines) + "\n"


def _plan_source(tasks: list[SubTask]) -> str:
    if all(task.task_id.startswith("auto-") for task in tasks):
        return "legacy template"
    if all(task.task_id.startswith("direct-") for task in tasks):
        return "direct routing"
    return "LLM planner/config"


def _memory_writer(config: Mapping[str, Any]) -> OrchestratorMemoryWriter | None:
    writer = config.get("orchestrator_memory_writer")
    if writer is None:
        return None
    return cast(OrchestratorMemoryWriter, writer)


async def _memory_start_run_for_messages(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    tasks: list[SubTask],
    messages: list[ChatMessage],
) -> None:
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        run_context.memory_run_id = await writer.start_run(
            user_request=_latest_user_request(messages),
            plan_source=_plan_source(tasks),
            tasks=tasks,
        )
    except Exception:  # noqa: BLE001
        run_context.memory_run_id = None


async def _memory_record_task_started(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    task: SubTask,
    agent_id: str,
    attempt_index: int,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        await writer.record_task_started(
            run_id=run_context.memory_run_id,
            task=task,
            agent_id=agent_id,
            attempt_index=attempt_index,
        )
    except Exception:  # noqa: BLE001
        return


async def _memory_record_task_result(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    task: SubTask,
    result: TaskResult,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        await writer.record_task_result(
            run_id=run_context.memory_run_id,
            task=task,
            result=result,
        )
    except Exception:  # noqa: BLE001
        return


async def _memory_finish_run(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    status: str,
    final_summary: str,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = _memory_writer(config)
    if writer is None:
        return
    try:
        await writer.finish_run(
            run_id=run_context.memory_run_id,
            status=status,
            final_summary=final_summary,
        )
    except Exception:  # noqa: BLE001
        return


def _agent_header_text(task: SubTask, agent_id: str | None = None) -> str:
    _ = task
    return f"@{agent_id or task.agent_id}\n\n"


def _failure_text(task: SubTask, reason: str, agent_id: str | None = None) -> str:
    _ = task
    return f"@{agent_id or task.agent_id} failed: {reason}\n"


def _fallback_summary_text() -> str:
    return "Execution summary\n\n- fallback: single agent mode\n"


def _summary_text(
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext | None = None,
) -> str:
    lines = ["Execution summary", ""]
    for task in tasks:
        state = task_states[task.task_id]
        result = run_context.results.get(task.task_id) if run_context else None
        if result is None or not result.attempts:
            lines.append(f"- {state.value}: @{task.agent_id} - {task.title}")
            continue

        final_attempt = result.attempts[-1]
        lines.append(f"- {state.value}: @{final_attempt.agent_id} - {task.title}")
        artifacts = _dedupe_strings(
            path for attempt in result.attempts for path in attempt.artifact_paths
        )
        missing = _dedupe_strings(
            path
            for attempt in result.attempts
            for path in attempt.missing_artifact_paths
        )
        if artifacts:
            lines.append(f"  artifacts: {', '.join(artifacts)}")
        if missing and state == TaskState.ARTIFACT_MISSING:
            lines.append(f"  missing: {', '.join(missing)}")
        if len(result.attempts) > 1 or state in {
            TaskState.FAILED,
            TaskState.ARTIFACT_MISSING,
        }:
            lines.append("  attempts:")
            for attempt in result.attempts:
                detail = (
                    f"  - attempt {attempt.attempt_index} "
                    f"@{attempt.agent_id}: {attempt.state.value}"
                )
                if attempt.error:
                    detail += f" - {attempt.error}"
                elif attempt.missing_artifact_paths:
                    detail += f" - missing {', '.join(attempt.missing_artifact_paths)}"
                lines.append(detail)
    return "\n".join(lines) + "\n"


async def _run_static_tasks(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    run_context: OrchestratorRunContext | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    task_states = {task.task_id: TaskState.PENDING for task in tasks}
    run_context = run_context or OrchestratorRunContext()
    for task in tasks:
        if not _dependencies_satisfied(task, task_states):
            task_states[task.task_id] = TaskState.SKIPPED
            skipped_result = TaskResult(
                task_id=task.task_id,
                title=task.title,
                final_state=TaskState.SKIPPED,
            )
            run_context.record(skipped_result)
            await _memory_record_task_result(config, run_context, task, skipped_result)
            continue

        async for chunk, updated_block_index in _run_task(
            config,
            task,
            messages,
            next_block_index,
            run_context,
            workspace_path,
            tool_specs,
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index
        task_states[task.task_id] = run_context.results[task.task_id].final_state

    final_summary = _summary_text(tasks, task_states, run_context)
    await _memory_finish_run(config, run_context, "done", final_summary)
    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        final_summary,
    ):
        yield chunk, updated_block_index


async def _remapped_sub_stream(
    sub_adapter: BaseAgentAdapter,
    task: SubTask,
    agent_id: str,
    call_id_prefix: str,
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    attempt: TaskAttempt,
) -> AsyncIterator[tuple[StreamChunk, int, bool]]:
    index_map: dict[int, int] = {}
    open_block_index: int | None = None
    try:
        async for chunk in sub_adapter.stream(
            messages,
            system_prompt=None,
            config=None,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
        ):
            if chunk.event_type in {"start", "done"}:
                continue
            if chunk.event_type == "error":
                if open_block_index is not None:
                    yield StreamChunk(
                        event_type="block_end", block_index=open_block_index
                    ), next_block_index, False
                    open_block_index = None
                attempt.error = _error_reason(chunk)
                attempt.state = TaskState.FAILED
                failure_text = _failure_text(task, attempt.error, agent_id)
                for failure_chunk in _text_block(next_block_index, failure_text):
                    yield failure_chunk, next_block_index + 1, True
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                _accumulate_tool_event(attempt, chunk)
                yield _remap_tool_call_id(chunk, call_id_prefix), next_block_index, False
                continue
            if chunk.event_type == "heartbeat":
                yield chunk, next_block_index, False
                continue
            if chunk.event_type not in {"block_start", "delta", "block_end"}:
                continue
            _accumulate_text_event(attempt, chunk)
            remapped, next_block_index = _remap_block_index(
                chunk,
                index_map,
                next_block_index,
            )
            if remapped.event_type == "block_start":
                open_block_index = remapped.block_index
            elif remapped.event_type == "block_end":
                open_block_index = None
            yield remapped, next_block_index, False
    except Exception as exc:
        if open_block_index is not None:
            yield StreamChunk(
                event_type="block_end", block_index=open_block_index
            ), next_block_index, False
            open_block_index = None
        attempt.error = str(exc)
        attempt.state = TaskState.FAILED
        failure_text = _failure_text(task, str(exc), agent_id)
        for failure_chunk in _text_block(next_block_index, failure_text):
            yield failure_chunk, next_block_index + 1, True
        return


async def _run_task(
    config: Mapping[str, Any],
    task: SubTask,
    messages: list[ChatMessage],
    next_block_index: int,
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    *,
    call_id_prefix: str | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    task_result = TaskResult(task_id=task.task_id, title=task.title)
    fallback_agents = _task_fallback_agent_ids(config)
    max_attempts = _max_task_attempts(config)
    attempted_agents: set[str] = set()

    for attempt_index in range(1, max_attempts + 1):
        agent_id = _agent_for_attempt(task, fallback_agents, attempted_agents)
        if agent_id is None:
            break
        attempted_agents.add(agent_id)

        attempt = TaskAttempt(attempt_index=attempt_index, agent_id=agent_id)
        task_result.attempts.append(attempt)
        await _memory_record_task_started(
            config,
            run_context,
            task,
            agent_id,
            attempt_index,
        )

        yield _agent_switch(task, agent_id), next_block_index
        for chunk, updated_block_index in _text_block_with_next(
            next_block_index,
            _agent_header_text(task, agent_id),
        ):
            yield chunk, updated_block_index
        next_block_index += 1

        try:
            sub_adapter = await _get_sub_adapter(config, agent_id)
        except Exception as exc:
            attempt.state = TaskState.FAILED
            attempt.error = str(exc)
            for chunk, updated_block_index in _text_block_with_next(
                next_block_index,
                _failure_text(task, str(exc), agent_id),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
        else:
            sub_messages = _task_messages(
                task,
                messages,
                run_context,
                config,
                previous_attempt=task_result.attempts[-2]
                if len(task_result.attempts) > 1
                else None,
            )
            task_failed = False
            async for chunk, updated_block_index, subtask_failed in _remapped_sub_stream(
                sub_adapter,
                task,
                agent_id,
                _attempt_call_id_prefix(
                    task.task_id,
                    attempt_index,
                    call_id_prefix=call_id_prefix,
                ),
                sub_messages,
                next_block_index,
                workspace_path,
                tool_specs,
                attempt,
            ):
                next_block_index = updated_block_index
                task_failed = subtask_failed
                yield chunk, updated_block_index
            if task_failed:
                attempt.state = TaskState.FAILED
            else:
                _finalize_artifact_candidates(attempt, task)
                _check_attempt_artifacts(attempt, workspace_path)

        task_result.final_state = attempt.state
        if attempt.state == TaskState.SUCCEEDED:
            break
        if not _can_retry_task(task_result, fallback_agents, max_attempts):
            break

    if not task_result.attempts:
        task_result.final_state = TaskState.FAILED
        task_result.attempts.append(
            TaskAttempt(
                attempt_index=1,
                agent_id=task.agent_id,
                state=TaskState.FAILED,
                error="no fallback agent available",
            )
        )
    run_context.record(task_result)
    await _memory_record_task_result(config, run_context, task, task_result)


def _task_messages(
    task: SubTask,
    messages: list[ChatMessage],
    run_context: OrchestratorRunContext,
    config: Mapping[str, Any],
    *,
    previous_attempt: TaskAttempt | None = None,
) -> list[ChatMessage]:
    task_message = ChatMessage(role="user", content=task.instruction)
    context_message = _task_result_context_message(
        run_context,
        task,
        config,
        previous_attempt=previous_attempt,
    )
    base_messages = [*messages] if task.include_history else []
    if context_message is not None:
        base_messages.append(context_message)
    base_messages.append(task_message)
    return base_messages


def _task_result_context_message(
    run_context: OrchestratorRunContext,
    task: SubTask,
    config: Mapping[str, Any],
    *,
    previous_attempt: TaskAttempt | None = None,
) -> ChatMessage | None:
    result_ids = _context_result_ids(run_context, task)
    lines: list[str] = []
    if result_ids:
        lines.append("Previous sub-agent results:")
        lines.append("")
        for task_id in result_ids:
            result = run_context.results.get(task_id)
            if result is None:
                continue
            item = _format_task_result_context(
                task_id,
                result,
                _task_result_item_max_chars(config),
            )
            if item:
                lines.append(item)
    if previous_attempt is not None:
        if lines:
            lines.append("")
        lines.append("Previous attempt failure:")
        lines.append(
            _format_attempt_context(previous_attempt, _task_result_item_max_chars(config))
        )
    if not lines:
        return None
    content = _truncate_preserving_edges(
        "\n".join(lines),
        _task_result_context_max_chars(config),
    )
    return ChatMessage(role="system", content=content)


def _context_result_ids(
    run_context: OrchestratorRunContext,
    task: SubTask,
) -> list[str]:
    if task.depends_on:
        return [task_id for task_id in task.depends_on if task_id in run_context.results]
    return [
        task_id
        for task_id in run_context.result_order
        if run_context.results[task_id].final_state != TaskState.PENDING
    ]


def _format_task_result_context(
    task_id: str,
    result: TaskResult,
    max_chars: int,
) -> str:
    if not result.attempts:
        return _truncate_preserving_edges(
            f"- {task_id} {result.final_state.value}",
            max_chars,
        )
    final_attempt = result.attempts[-1]
    lines = [
        f"- {task_id} @{final_attempt.agent_id} {result.final_state.value}",
    ]
    if final_attempt.text_preview:
        lines.append(f"  Text: {final_attempt.text_preview}")
    if final_attempt.tool_summaries:
        lines.append(f"  Tools: {'; '.join(final_attempt.tool_summaries[:4])}")
    if final_attempt.artifact_paths:
        lines.append(f"  Artifacts: {', '.join(final_attempt.artifact_paths)}")
    if final_attempt.error:
        lines.append(f"  Error: {final_attempt.error}")
    if final_attempt.missing_artifact_paths:
        lines.append(f"  Missing: {', '.join(final_attempt.missing_artifact_paths)}")
    return _truncate_preserving_edges("\n".join(lines), max_chars)


def _format_attempt_context(attempt: TaskAttempt, max_chars: int) -> str:
    text = (
        f"- attempt {attempt.attempt_index} @{attempt.agent_id} "
        f"{attempt.state.value}"
    )
    if attempt.error:
        text += f": {attempt.error}"
    elif attempt.missing_artifact_paths:
        text += f": missing {', '.join(attempt.missing_artifact_paths)}"
    return _truncate_preserving_edges(text, max_chars)


def _task_fallback_agent_ids(config: Mapping[str, Any]) -> list[str]:
    value = config.get("task_fallback_agent_ids")
    if not isinstance(value, list):
        return []
    return _dedupe_strings(
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip() and item.strip() != "orchestrator"
    )


def _max_task_attempts(config: Mapping[str, Any]) -> int:
    value = config.get("max_task_attempts", DEFAULT_MAX_TASK_ATTEMPTS)
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_MAX_TASK_ATTEMPTS
    return int(min(max(value, 1), MAX_TASK_ATTEMPTS_LIMIT))


def _task_result_context_max_chars(config: Mapping[str, Any]) -> int:
    return _positive_int_config(
        config,
        "task_result_context_max_chars",
        DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS,
    )


def _task_result_item_max_chars(config: Mapping[str, Any]) -> int:
    return _positive_int_config(
        config,
        "task_result_item_max_chars",
        DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    )


def _positive_int_config(
    config: Mapping[str, Any],
    key: str,
    default: int,
) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return int(value)


def _agent_for_attempt(
    task: SubTask,
    fallback_agents: list[str],
    attempted_agents: set[str],
) -> str | None:
    if not attempted_agents:
        return task.agent_id
    for agent_id in fallback_agents:
        if agent_id not in attempted_agents:
            return agent_id
    return None


def _can_retry_task(
    result: TaskResult,
    fallback_agents: list[str],
    max_attempts: int,
) -> bool:
    if not fallback_agents or len(result.attempts) >= max_attempts:
        return False
    return result.final_state in {TaskState.FAILED, TaskState.ARTIFACT_MISSING}


def _attempt_call_id_prefix(
    task_id: str,
    attempt_index: int,
    *,
    call_id_prefix: str | None = None,
) -> str:
    base = call_id_prefix or task_id
    if attempt_index == 1:
        return base
    return f"{base}.attempt-{attempt_index}"


def _accumulate_text_event(attempt: TaskAttempt, chunk: StreamChunk) -> None:
    if chunk.text_delta:
        attempt.text_preview = _append_limited(
            attempt.text_preview,
            chunk.text_delta,
            DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
        )
        attempt.artifact_paths.extend(_extract_artifact_paths_from_text(chunk.text_delta))
    if chunk.code_delta:
        attempt.text_preview = _append_limited(
            attempt.text_preview,
            chunk.code_delta,
            DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
        )
    if chunk.metadata:
        attempt.artifact_paths.extend(_extract_artifact_paths_from_mapping(chunk.metadata))


def _accumulate_tool_event(attempt: TaskAttempt, chunk: StreamChunk) -> None:
    if chunk.event_type == "tool_call":
        summary = _tool_call_summary(chunk)
        if summary:
            attempt.tool_summaries.append(summary)
        if chunk.tool_arguments:
            attempt.artifact_paths.extend(
                _extract_artifact_paths_from_mapping(chunk.tool_arguments)
            )
    elif chunk.event_type == "tool_result":
        summary = _tool_result_summary(chunk)
        if summary:
            attempt.tool_summaries.append(summary)
        if chunk.tool_output:
            attempt.artifact_paths.extend(
                _extract_artifact_paths_from_text(chunk.tool_output)
            )


def _tool_call_summary(chunk: StreamChunk) -> str:
    name = chunk.tool_name or "tool"
    path_bits = []
    if chunk.tool_arguments:
        path_bits = _extract_artifact_paths_from_mapping(chunk.tool_arguments)
    if path_bits:
        return f"{name}({', '.join(path_bits[:3])})"
    return name


def _tool_result_summary(chunk: StreamChunk) -> str:
    status = chunk.tool_status or "unknown"
    output = _truncate_preserving_edges(chunk.tool_output or "", 160)
    if output:
        return f"result {status}: {output}"
    return f"result {status}"


def _finalize_artifact_candidates(attempt: TaskAttempt, task: SubTask) -> None:
    candidates: list[str] = []
    if task.expected_output:
        candidates.extend(_extract_artifact_paths_from_text(task.expected_output))
    candidates.extend(_extract_artifact_paths_from_text(task.instruction))
    candidates.extend(attempt.artifact_paths)
    attempt.artifact_paths = _dedupe_strings(candidates)


def _check_attempt_artifacts(
    attempt: TaskAttempt,
    workspace_path: Path | None,
) -> None:
    if workspace_path is None or not attempt.artifact_paths:
        attempt.state = TaskState.SUCCEEDED
        return
    missing = [
        path
        for path in attempt.artifact_paths
        if not (workspace_path / path).exists()
    ]
    attempt.missing_artifact_paths = missing
    if missing:
        attempt.state = TaskState.ARTIFACT_MISSING
        attempt.error = f"missing artifact: {', '.join(missing)}"
        return
    attempt.state = TaskState.SUCCEEDED


def _extract_artifact_paths_from_mapping(value: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    for key, item in value.items():
        normalized_key = str(key).lower()
        if normalized_key in ARTIFACT_PATH_KEYS and isinstance(item, str):
            candidate = _normalize_artifact_path(item)
            if candidate is not None:
                paths.append(candidate)
        elif isinstance(item, Mapping):
            paths.extend(_extract_artifact_paths_from_mapping(item))
        elif isinstance(item, list):
            for child in item:
                if isinstance(child, Mapping):
                    paths.extend(_extract_artifact_paths_from_mapping(child))
                elif isinstance(child, str):
                    paths.extend(_extract_artifact_paths_from_text(child))
    return _dedupe_strings(paths)


def _extract_artifact_paths_from_text(text: str) -> list[str]:
    return _dedupe_strings(
        path
        for match in ARTIFACT_PATH_PATTERN.finditer(text)
        if (path := _normalize_artifact_path(match.group(1))) is not None
    )


def _normalize_artifact_path(raw_path: str) -> str | None:
    cleaned = raw_path.strip().strip("`'\".,;:)]}")
    if not cleaned:
        return None
    cleaned = cleaned.replace("\\", "/")
    candidate = Path(cleaned)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    parts = [part for part in cleaned.split("/") if part]
    if not parts or any(part in SENSITIVE_ARTIFACT_PARTS for part in parts):
        return None
    if any(part.startswith(".") and part not in {".well-known"} for part in parts):
        return None
    return "/".join(parts)


def _append_limited(existing: str, addition: str, max_chars: int) -> str:
    combined = f"{existing}{addition}"
    return _truncate_preserving_edges(combined, max_chars)


def _truncate_preserving_edges(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 20:
        return normalized[:max_chars]
    head_len = max_chars // 2
    tail_len = max_chars - head_len - 5
    return f"{normalized[:head_len].rstrip()} ... {normalized[-tail_len:].lstrip()}"


def _dedupe_strings(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _remap_block_index(
    chunk: StreamChunk,
    index_map: dict[int, int],
    next_block_index: int,
) -> tuple[StreamChunk, int]:
    if chunk.block_index is None:
        return chunk, next_block_index

    mapped_index = index_map.get(chunk.block_index)
    if mapped_index is None:
        mapped_index = next_block_index
        index_map[chunk.block_index] = mapped_index
        next_block_index += 1
    return chunk.model_copy(update={"block_index": mapped_index}), next_block_index


def _remap_tool_call_id(chunk: StreamChunk, task_id: str) -> StreamChunk:
    if not chunk.call_id:
        return chunk
    return chunk.model_copy(update={"call_id": f"{task_id}.{chunk.call_id}"})


def _error_reason(chunk: StreamChunk) -> str:
    return chunk.error or chunk.error_code or "unknown error"


def _error_code(exc: ValueError) -> str:
    return str(exc).split(":", maxsplit=1)[0]
