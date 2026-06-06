"""Adapter lookup and fallback streaming helpers for Orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar, cast

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator._internal.execution.group_messages import (
    child_message_chunk,
    finish_group_message,
    group_messages_enabled,
    start_group_message,
)
from app.agents.orchestrator._internal.streams import (
    attach_agent_id,
    remap_block_index,
    remap_tool_call_id,
)
from app.agents.orchestrator.types import AdapterFactory
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

T = TypeVar("T")


def ensure_adapter_source(config: Mapping[str, Any]) -> None:
    if isinstance(config.get("sub_adapters"), Mapping):
        return
    if callable(config.get("adapter_factory")):
        return
    raise ValueError(
        "missing_sub_adapters: config.sub_adapters or config.adapter_factory is required"
    )


async def get_sub_adapter(
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
        adapter = await _with_db_lock(
            config,
            lambda: cast(AdapterFactory, factory)(agent_id),
        )
        if isinstance(adapter, BaseAgentAdapter):
            return adapter
        raise ValueError("adapter_factory returned a non-BaseAgentAdapter value")

    raise ValueError(f"no injected adapter for agent {agent_id!r}")


async def _with_db_lock(
    config: Mapping[str, Any],
    call: Callable[[], T | Awaitable[T]],
) -> T:
    lock = config.get("orchestrator_db_lock")
    if lock is None:
        result = call()
        return await result if isinstance(result, Awaitable) else result
    async with cast(Any, lock):
        result = call()
        return await result if isinstance(result, Awaitable) else result


def has_fallback(config: Mapping[str, Any]) -> bool:
    if isinstance(config.get("fallback_adapter"), BaseAgentAdapter):
        return True
    if callable(config.get("fallback_adapter_factory")):
        return True
    return False


async def run_fallback(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    fallback_agent_id = _fallback_agent_id(config)

    try:
        fallback_adapter = await _get_fallback_adapter(config)
    except Exception:
        for chunk, updated_block_index in _text_block_with_next(
            next_block_index,
            _fallback_failure_text(fallback_agent_id),
            agent_id=fallback_agent_id,
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

    child_message_id: str | None = None
    child_next_block_index = 0
    if group_messages_enabled(config) and fallback_agent_id != "orchestrator":
        child_message_id, start_chunk = await start_group_message(
            config,
            agent_id=fallback_agent_id,
        )
        if start_chunk is not None:
            yield start_chunk, next_block_index

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
                    end_chunk = StreamChunk(
                        event_type="block_end",
                        block_index=open_block_index,
                        agent_id=fallback_agent_id,
                    )
                    if child_message_id:
                        yield child_message_chunk(
                            end_chunk,
                            message_id=child_message_id,
                            agent_id=fallback_agent_id,
                        ), next_block_index
                    else:
                        yield end_chunk, next_block_index
                    open_block_index = None
                failure_text = _fallback_failure_text(fallback_agent_id)
                failure_block_index = (
                    child_next_block_index if child_message_id else next_block_index
                )
                for failure_chunk in _text_block(
                    failure_block_index,
                    failure_text,
                    agent_id=fallback_agent_id,
                ):
                    if child_message_id:
                        yield child_message_chunk(
                            failure_chunk,
                            message_id=child_message_id,
                            agent_id=fallback_agent_id,
                        ), next_block_index
                    else:
                        yield failure_chunk, next_block_index + 1
                if child_message_id:
                    error_chunk = await finish_group_message(
                        config,
                        child_message_id,
                        status="error",
                        error=chunk.error or chunk.error_code,
                        error_code=chunk.error_code,
                    )
                    if error_chunk is not None:
                        yield error_chunk, next_block_index
                return
            if chunk.event_type in {"tool_call", "tool_result"}:
                remapped = remap_tool_call_id(chunk, "fallback")
                output = attach_agent_id(remapped, fallback_agent_id)
                if child_message_id:
                    yield child_message_chunk(
                        output,
                        message_id=child_message_id,
                        agent_id=fallback_agent_id,
                    ), next_block_index
                else:
                    yield output, next_block_index
                continue
            if chunk.event_type == "heartbeat":
                output = attach_agent_id(chunk, fallback_agent_id)
                if child_message_id:
                    yield child_message_chunk(
                        output,
                        message_id=child_message_id,
                        agent_id=fallback_agent_id,
                    ), next_block_index
                else:
                    yield output, next_block_index
                continue
            if chunk.event_type not in {"block_start", "delta", "block_end"}:
                continue
            remap_start_index = child_next_block_index if child_message_id else next_block_index
            remapped, updated_block_index = remap_block_index(
                chunk,
                index_map,
                remap_start_index,
            )
            if child_message_id:
                child_next_block_index = updated_block_index
            else:
                next_block_index = updated_block_index
            if remapped.event_type == "block_start":
                open_block_index = remapped.block_index
            elif remapped.event_type == "block_end":
                open_block_index = None
            output = attach_agent_id(remapped, fallback_agent_id)
            if child_message_id:
                yield child_message_chunk(
                    output,
                    message_id=child_message_id,
                    agent_id=fallback_agent_id,
                ), next_block_index
            else:
                yield output, next_block_index
    except Exception:
        if open_block_index is not None:
            end_chunk = StreamChunk(
                event_type="block_end",
                block_index=open_block_index,
                agent_id=fallback_agent_id,
            )
            if child_message_id:
                yield child_message_chunk(
                    end_chunk,
                    message_id=child_message_id,
                    agent_id=fallback_agent_id,
                ), next_block_index
            else:
                yield end_chunk, next_block_index
            open_block_index = None
        failure_block_index = child_next_block_index if child_message_id else next_block_index
        for chunk, updated_block_index in _text_block_with_next(
            failure_block_index,
            _fallback_failure_text(fallback_agent_id),
            agent_id=fallback_agent_id,
        ):
            if child_message_id:
                child_next_block_index = updated_block_index
                yield child_message_chunk(
                    chunk,
                    message_id=child_message_id,
                    agent_id=fallback_agent_id,
                ), next_block_index
            else:
                yield chunk, updated_block_index
        if child_message_id:
            error_chunk = await finish_group_message(
                config,
                child_message_id,
                status="error",
                error=_fallback_failure_text(fallback_agent_id).strip(),
            )
            if error_chunk is not None:
                yield error_chunk, next_block_index
            child_message_id = None
    if child_message_id:
        done_chunk = await finish_group_message(config, child_message_id)
        if done_chunk is not None:
            yield done_chunk, next_block_index


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


def _fallback_agent_id(config: Mapping[str, Any]) -> str:
    agent_id = config.get("fallback_agent_id")
    if isinstance(agent_id, str) and agent_id:
        return agent_id
    return "fallback"


def _fallback_failure_text(agent_id: str) -> str:
    return (
        f"{agent_id} 在“fallback”阶段未能完成。可以重试这条消息；"
        "如果持续失败，请检查该 Agent 的运行配置和 workspace 状态。\n"
    )


def _text_block(
    block_index: int,
    text: str,
    *,
    agent_id: str = "orchestrator",
) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="delta",
            block_index=block_index,
            text_delta=text,
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="block_end",
            block_index=block_index,
            agent_id=agent_id,
        ),
    )


def _text_block_with_next(
    block_index: int,
    text: str,
    *,
    agent_id: str = "orchestrator",
) -> tuple[tuple[StreamChunk, int], ...]:
    next_block_index = block_index + 1
    return tuple(
        (chunk, next_block_index)
        for chunk in _text_block(block_index, text, agent_id=agent_id)
    )


def _error_reason(chunk: StreamChunk) -> str:
    return chunk.error or chunk.error_code or "unknown error"
