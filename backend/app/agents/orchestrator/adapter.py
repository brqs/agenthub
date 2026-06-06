"""Orchestrator injection-based sub-agent dispatch."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator._internal.execution.adapters import (
    ensure_adapter_source as _ensure_adapter_source,
)
from app.agents.orchestrator._internal.execution.adapters import (
    has_fallback as _has_fallback,
)
from app.agents.orchestrator._internal.execution.adapters import (
    run_fallback as _run_fallback,
)
from app.agents.orchestrator._internal.execution.attempts import (
    positive_int_config as _positive_int_config,
)
from app.agents.orchestrator._internal.execution.events import error_code as _error_code
from app.agents.orchestrator._internal.execution.events import error_reason as _error_reason
from app.agents.orchestrator._internal.execution.process_block import (
    process_block_end as _process_block_end,
)
from app.agents.orchestrator._internal.execution.process_block import (
    process_block_start as _process_block_start,
)
from app.agents.orchestrator._internal.execution.process_block import (
    process_step_delta as _process_step_delta,
)
from app.agents.orchestrator._internal.execution.process_block import (
    route_process_block as _route_process_block,
)
from app.agents.orchestrator._internal.execution.process_block import (
    route_process_step as _route_process_step,
)
from app.agents.orchestrator._internal.execution.summary import (
    fallback_summary_text as _fallback_summary_text,
)
from app.agents.orchestrator._internal.execution.summary import (
    format_task_result_context as _format_task_result_context,
)
from app.agents.orchestrator._internal.execution.summary import (
    plan_source as _plan_source,
)
from app.agents.orchestrator._internal.execution.summary import (
    planning_text as _planning_text,
)
from app.agents.orchestrator._internal.execution.summary import (
    summary_text as _summary_text,
)
from app.agents.orchestrator._internal.memory import (
    start_run as _memory_start_run,
)
from app.agents.orchestrator._internal.react import react_enabled, run_react_loop
from app.agents.orchestrator._internal.routing.custom_agent import (
    custom_agent_result_text as _custom_agent_result_text,
)
from app.agents.orchestrator._internal.routing.custom_agent import (
    custom_agent_tool_arguments as _custom_agent_tool_arguments,
)
from app.agents.orchestrator._internal.routing.direct_answer import (
    run_direct_answer as _run_direct_answer,
)
from app.agents.orchestrator._internal.routing.direct_answer import (
    should_direct_answer as _should_direct_answer,
)
from app.agents.orchestrator._internal.routing.platform_facts import (
    platform_fact_intent,
    platform_fact_text,
)
from app.agents.orchestrator._internal.tools.loop import (
    run_orchestrator_tool_loop,
    tool_calling_enabled,
)
from app.agents.orchestrator.clarification import (
    maybe_handle_clarification as _maybe_handle_clarification,
)
from app.agents.orchestrator.execution import (
    _run_static_tasks,
    _run_task,
    _task_card_block,
    _text_block,
    _text_block_with_next,
)
from app.agents.orchestrator.quality import run_quality_gate
from app.agents.orchestrator.task_planning import (
    PlannerResolutionError,
)
from app.agents.orchestrator.task_planning import (
    agent_id_list as _agent_id_list,
)
from app.agents.orchestrator.task_planning import (
    balance_requested_multi_agent_plan as _balance_requested_multi_agent_plan,
)
from app.agents.orchestrator.task_planning import (
    expand_agent_review_tasks as _expand_agent_review_tasks,
)
from app.agents.orchestrator.task_planning import (
    explicit_agent_mentions as _explicit_agent_mentions,
)
from app.agents.orchestrator.task_planning import (
    has_task_intent as _has_task_intent,
)
from app.agents.orchestrator.task_planning import (
    latest_user_request as _latest_user_request,
)
from app.agents.orchestrator.task_planning import (
    resolve_tasks as _resolve_tasks,
)
from app.agents.orchestrator.task_planning import (
    should_direct_answer_after_planner_error as _should_direct_answer_after_planner_error,
)
from app.agents.orchestrator.task_planning import (
    strip_orchestrator_mention as _strip_orchestrator_mention,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


def _route_process_chunks(
    config: Mapping[str, Any],
    block_index: int,
    messages: list[ChatMessage],
    route: str,
    *,
    status: str = "done",
    detail: str | None = None,
) -> tuple[tuple[StreamChunk, int], ...]:
    process_start = _process_block_start(
        config,
        block_index,
        _route_process_block(route, messages, status=status, detail=detail),
    )
    if process_start is None:
        return ()
    start_chunk, next_block_index = process_start
    process_block_index = start_chunk.block_index
    chunks: list[tuple[StreamChunk, int]] = [(start_chunk, next_block_index)]
    step_chunk = _process_step_delta(
        config,
        process_block_index,
        _route_process_step(route, status=status, detail=detail),
    )
    if step_chunk is not None:
        chunks.append((step_chunk, next_block_index))
    end_chunk = _process_block_end(config, process_block_index)
    if end_chunk is not None:
        chunks.append((end_chunk, next_block_index))
    return tuple(chunks)


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
        clarification = await _maybe_handle_clarification(
            merged_config,
            messages,
            next_block_index,
            workspace_path,
            latest_user_request=_latest_user_request,
            has_task_intent=_has_task_intent,
        )
        if clarification is not None:
            for chunk in clarification.chunks:
                yield chunk
            next_block_index = clarification.next_block_index
            if clarification.done:
                yield StreamChunk(
                    event_type="done",
                    agent_id=self.agent_id,
                    total_blocks=next_block_index,
                )
                return
            if clarification.continue_messages is not None:
                messages = clarification.continue_messages

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
            for chunk, updated_block_index in _route_process_chunks(
                merged_config,
                next_block_index,
                messages,
                "platform_fact",
            ):
                next_block_index = updated_block_index
                yield chunk
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
        if _should_direct_answer(
            merged_config,
            messages,
            latest_user_request=_latest_user_request,
            agent_id_list=_agent_id_list,
            explicit_agent_mentions=_explicit_agent_mentions,
            strip_orchestrator_mention=_strip_orchestrator_mention,
            has_task_intent=_has_task_intent,
        ):
            for chunk, updated_block_index in _route_process_chunks(
                merged_config,
                next_block_index,
                messages,
                "direct_answer",
            ):
                next_block_index = updated_block_index
                yield chunk
            async for chunk, updated_block_index, failed in _run_direct_answer(
                merged_config,
                messages,
                self.effective_system_prompt(system_prompt),
                next_block_index,
                latest_user_request=_latest_user_request,
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

        custom_agent_args = _custom_agent_tool_arguments(_latest_user_request(messages))
        if merged_config.get("tasks") is None and custom_agent_args is not None:
            call_id = "orch.custom_agent.create"
            yield StreamChunk(
                event_type="tool_call",
                call_id=call_id,
                tool_name="create_custom_agent",
                tool_arguments=custom_agent_args,
                agent_id=self.agent_id,
            )
            executor = merged_config.get("orchestrator_platform_tool_executor")
            if executor is None:
                tool_status = "error"
                tool_output = json.dumps(
                    {
                        "status": "error",
                        "error": "platform tool executor is not available: create_custom_agent",
                    },
                    ensure_ascii=False,
                )
            else:
                result = await executor("create_custom_agent", custom_agent_args)
                tool_status = result.status
                tool_output = result.output
            yield StreamChunk(
                event_type="tool_result",
                call_id=call_id,
                tool_name="create_custom_agent",
                tool_status=tool_status,
                tool_output=tool_output,
                tool_output_truncated=False,
                agent_id=self.agent_id,
            )
            final_text = _custom_agent_result_text(tool_status, tool_output)
            for chunk, updated_block_index in _route_process_chunks(
                merged_config,
                next_block_index,
                messages,
                "custom_agent",
                status="done" if tool_status == "ok" else "error",
            ):
                next_block_index = updated_block_index
                yield chunk
            for chunk in _text_block(next_block_index, final_text):
                yield chunk
            next_block_index += 1
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
            if _should_direct_answer_after_planner_error(
                merged_config,
                exc,
                _latest_user_request(messages),
            ):
                for chunk, updated_block_index in _route_process_chunks(
                    merged_config,
                    next_block_index,
                    messages,
                    "direct_answer",
                ):
                    next_block_index = updated_block_index
                    yield chunk
                async for chunk, updated_block_index, failed in _run_direct_answer(
                    merged_config,
                    messages,
                    self.effective_system_prompt(system_prompt),
                    next_block_index,
                    latest_user_request=_latest_user_request,
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
                for process_chunk, updated_block_index in _route_process_chunks(
                    merged_config,
                    next_block_index,
                    messages,
                    "fallback",
                    status="partial",
                ):
                    next_block_index = updated_block_index
                    yield process_chunk
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
                for process_chunk, updated_block_index in _route_process_chunks(
                    merged_config,
                    next_block_index,
                    messages,
                    "fallback",
                    status="partial",
                ):
                    next_block_index = updated_block_index
                    yield process_chunk
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

        tasks = _expand_agent_review_tasks(merged_config, tasks)
        tasks = _balance_requested_multi_agent_plan(
            tasks,
            merged_config,
            _latest_user_request(messages),
        )

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
        await _memory_start_run(
            merged_config,
            run_context,
            user_request=_latest_user_request(messages),
            plan_source=_plan_source(tasks),
            tasks=tasks,
        )
        for chunk, updated_block_index in _task_card_block(next_block_index, tasks):
            next_block_index = updated_block_index
            yield chunk
        for chunk in _text_block(next_block_index, _planning_text(tasks)):
            yield chunk
        next_block_index += 1

        use_parallel_static = (
            merged_config.get("orchestrator_parallel_enabled") is True
            and len(tasks) > 1
        )
        if react_enabled(merged_config) and not use_parallel_static:
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
                if chunk.event_type == "error":
                    return
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
                if chunk.event_type == "error":
                    return
        async for chunk, updated_block_index in run_quality_gate(
            merged_config,
            messages,
            next_block_index,
            workspace_path,
            tool_specs,
            run_context,
            run_task=_run_task,
            text_block_with_next=_text_block_with_next,
            positive_int_config=_positive_int_config,
        ):
            next_block_index = updated_block_index
            yield chunk
            if chunk.event_type == "error":
                return
        yield StreamChunk(
            event_type="done", agent_id=self.agent_id, total_blocks=next_block_index
        )
