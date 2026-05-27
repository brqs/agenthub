"""Orchestrator injection-based sub-agent dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

AdapterFactory = Callable[[str], BaseAgentAdapter | Awaitable[BaseAgentAdapter]]


class TaskState(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class SubTask:
    task_id: str
    agent_id: str
    title: str
    instruction: str
    depends_on: tuple[str, ...] = ()
    priority: int = 0
    expected_output: str | None = None
    include_history: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SubTask:
        return cls(
            task_id=_required_str(raw, "task_id"),
            agent_id=_required_str(raw, "agent_id"),
            title=_required_str(raw, "title"),
            instruction=_required_str(raw, "instruction"),
            depends_on=_depends_on(raw),
            priority=_priority(raw),
            expected_output=_optional_str(raw, "expected_output"),
            include_history=_include_history(raw),
        )


@dataclass(slots=True)
class TaskRunResult:
    state: TaskState = TaskState.PENDING


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
        try:
            tasks = _parse_tasks(merged_config, messages)
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

        for chunk in _text_block(next_block_index, _planning_text(tasks)):
            yield chunk
        next_block_index += 1

        task_states = {task.task_id: TaskState.PENDING for task in tasks}
        for task in tasks:
            if not _dependencies_satisfied(task, task_states):
                task_states[task.task_id] = TaskState.SKIPPED
                continue

            result = TaskRunResult()
            async for chunk, updated_block_index in _run_task(
                merged_config,
                task,
                messages,
                next_block_index,
                result,
                workspace_path,
                tool_specs,
            ):
                next_block_index = updated_block_index
                yield chunk
            task_states[task.task_id] = result.state

        for chunk in _text_block(next_block_index, _summary_text(tasks, task_states)):
            yield chunk
        next_block_index += 1
        yield StreamChunk(
            event_type="done", agent_id=self.agent_id, total_blocks=next_block_index
        )


def _required_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid_task_plan: task.{key} must be a non-empty string")
    return value


def _optional_str(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid_task_plan: task.{key} must be a string")
    return value


def _depends_on(raw: Mapping[str, Any]) -> tuple[str, ...]:
    value = raw.get("depends_on", [])
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("invalid_task_plan: task.depends_on must be a list")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("invalid_task_plan: task.depends_on must contain strings")
    return tuple(value)


def _priority(raw: Mapping[str, Any]) -> int:
    value: object = raw.get("priority", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid_task_plan: task.priority must be an integer")
    return value


def _include_history(raw: Mapping[str, Any]) -> bool:
    value = raw.get("include_history", True)
    if not isinstance(value, bool):
        raise ValueError("invalid_task_plan: task.include_history must be a boolean")
    return value


def _parse_tasks(config: Mapping[str, Any], messages: list[ChatMessage]) -> list[SubTask]:
    raw_tasks = config.get("tasks")
    if raw_tasks is None:
        return _derive_tasks(config, messages)
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("missing_task_plan: config.tasks must be a non-empty list")

    tasks: list[SubTask] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, Mapping):
            raise ValueError("invalid_task_plan: each task must be an object")
        tasks.append(SubTask.from_mapping(cast(Mapping[str, Any], raw_task)))
    _ensure_unique_task_ids(tasks)
    return sorted(tasks, key=lambda task: task.priority)


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


def _agent_switch(task: SubTask) -> StreamChunk:
    return StreamChunk(
        event_type="agent_switch",
        from_agent="orchestrator",
        to_agent=task.agent_id,
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
    lines = [f"Planned {len(tasks)} sub-task(s):"]
    for index, task in enumerate(tasks, 1):
        lines.append(f"{index}. @{task.agent_id} - {task.title}")
    return "\n".join(lines) + "\n"


def _agent_header_text(task: SubTask) -> str:
    return f"@{task.agent_id}\n\n"


def _failure_text(task: SubTask, reason: str) -> str:
    return f"@{task.agent_id} failed: {reason}\n"


def _fallback_summary_text() -> str:
    return "Execution summary\n\n- fallback: single agent mode\n"


def _summary_text(
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
) -> str:
    lines = ["Execution summary", ""]
    for task in tasks:
        state = task_states[task.task_id]
        lines.append(f"- {state.value}: @{task.agent_id} - {task.title}")
    return "\n".join(lines) + "\n"


async def _remapped_sub_stream(
    sub_adapter: BaseAgentAdapter,
    task: SubTask,
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
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
                failure_text = _failure_text(task, _error_reason(chunk))
                for failure_chunk in _text_block(next_block_index, failure_text):
                    yield failure_chunk, next_block_index + 1, True
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                yield _remap_tool_call_id(chunk, task.task_id), next_block_index, False
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
            open_block_index = None
        failure_text = _failure_text(task, str(exc))
        for failure_chunk in _text_block(next_block_index, failure_text):
            yield failure_chunk, next_block_index + 1, True
        return


async def _run_task(
    config: Mapping[str, Any],
    task: SubTask,
    messages: list[ChatMessage],
    next_block_index: int,
    result: TaskRunResult,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    yield _agent_switch(task), next_block_index
    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        _agent_header_text(task),
    ):
        yield chunk, updated_block_index
    next_block_index += 1

    try:
        sub_adapter = await _get_sub_adapter(config, task.agent_id)
    except Exception as exc:
        result.state = TaskState.FAILED
        for chunk, updated_block_index in _text_block_with_next(
            next_block_index,
            _failure_text(task, str(exc)),
        ):
            yield chunk, updated_block_index
        return

    task_message = ChatMessage(role="user", content=task.instruction)
    sub_messages = [*messages, task_message] if task.include_history else [task_message]
    task_failed = False
    async for chunk, updated_block_index, subtask_failed in _remapped_sub_stream(
        sub_adapter,
        task,
        sub_messages,
        next_block_index,
        workspace_path,
        tool_specs,
    ):
        next_block_index = updated_block_index
        task_failed = subtask_failed
        yield chunk, updated_block_index
    result.state = TaskState.FAILED if task_failed else TaskState.SUCCEEDED


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
