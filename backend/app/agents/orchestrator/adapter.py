"""Orchestrator injection-based sub-agent dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator.adapters import (
    ensure_adapter_source as _ensure_adapter_source,
)
from app.agents.orchestrator.adapters import (
    has_fallback as _has_fallback,
)
from app.agents.orchestrator.adapters import (
    run_fallback as _run_fallback,
)
from app.agents.orchestrator.direct_answer import (
    run_direct_answer as _run_direct_answer,
)
from app.agents.orchestrator.direct_answer import (
    should_direct_answer as _should_direct_answer,
)
from app.agents.orchestrator.execution import (
    _error_code,
    _error_reason,
    _positive_int_config,
    _run_static_tasks,
    _run_task,
    _text_block,
    _text_block_with_next,
)
from app.agents.orchestrator.memory_hooks import (
    start_run as _memory_start_run,
)
from app.agents.orchestrator.platform_facts import (
    platform_fact_intent,
    platform_fact_text,
)
from app.agents.orchestrator.react import react_enabled, run_react_loop
from app.agents.orchestrator.summary import (
    fallback_summary_text as _fallback_summary_text,
)
from app.agents.orchestrator.summary import (
    format_task_result_context as _format_task_result_context,
)
from app.agents.orchestrator.summary import (
    plan_source as _plan_source,
)
from app.agents.orchestrator.summary import (
    planning_text as _planning_text,
)
from app.agents.orchestrator.summary import (
    summary_text as _summary_text,
)
from app.agents.orchestrator.task_planning import (
    PlannerResolutionError,
)
from app.agents.orchestrator.task_planning import (
    agent_id_list as _agent_id_list,
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
from app.agents.orchestrator.tool_loop import (
    run_orchestrator_tool_loop,
    tool_calling_enabled,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


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
        if _should_direct_answer(
            merged_config,
            messages,
            latest_user_request=_latest_user_request,
            agent_id_list=_agent_id_list,
            explicit_agent_mentions=_explicit_agent_mentions,
            strip_orchestrator_mention=_strip_orchestrator_mention,
            has_task_intent=_has_task_intent,
        ):
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
        await _memory_start_run(
            merged_config,
            run_context,
            user_request=_latest_user_request(messages),
            plan_source=_plan_source(tasks),
            tasks=tasks,
        )
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
