"""Orchestrator injection-based sub-agent dispatch."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping
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
from app.agents.orchestrator.quality import run_quality_gate
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

        tasks = _expand_agent_review_tasks(merged_config, tasks)

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


def _custom_agent_tool_arguments(user_request: str) -> dict[str, Any] | None:
    if not _looks_like_custom_agent_request(user_request):
        return None
    name = _extract_named_value(
        user_request,
        (
            r"(?:名字|名称|name)\s*(?:为|是|叫|=|:)\s*[\"'“”‘’]?([^，,。；;\n\"'“”‘’]+)",
        ),
    )
    provider = _extract_named_value(
        user_request,
        (
            r"provider\s*(?:使用|为|是|=|:)\s*[\"'“”‘’]?([A-Za-z0-9_-]+)",
            r"(?:提供商|类型)\s*(?:使用|为|是|=|:)\s*[\"'“”‘’]?([A-Za-z0-9_-]+)",
        ),
    )
    system_prompt = _extract_named_value(
        user_request,
        (
            r"system_prompt\s*(?:为|是|=|:)\s*[\"“](.+?)[\"”]",
            r"(?:系统提示词|角色设定)\s*(?:为|是|=|:)\s*[\"“](.+?)[\"”]",
        ),
    )
    if not name or not provider or not system_prompt:
        return None

    capabilities = _extract_capabilities(user_request)
    result: dict[str, Any] = {
        "name": name,
        "provider": provider,
        "system_prompt": system_prompt,
        "capabilities": capabilities,
        "config": {},
        "add_to_conversation": _should_add_custom_agent_to_conversation(user_request),
    }
    allowed_tools = _extract_allowed_tools(user_request)
    if allowed_tools is not None:
        result["allowed_tools"] = allowed_tools
    return result


def _looks_like_custom_agent_request(user_request: str) -> bool:
    lowered = user_request.lower()
    return (
        ("agent" in lowered or "智能体" in user_request or "代理" in user_request)
        and any(marker in user_request for marker in ("创建", "新建", "新增", "create"))
    )


def _extract_named_value(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if not match:
            continue
        value = match.group(1).strip()
        value = value.strip(" \t\r\n\"'“”‘’")
        if value:
            return value
    return None


def _extract_capabilities(user_request: str) -> list[str]:
    match = re.search(
        r"(?:capabilities|能力标签|能力)\s*(?:设置为|为|是|=|:)\s*([^。；;\n]+)",
        user_request,
        re.I,
    )
    if not match:
        return []
    raw = match.group(1)
    parts = re.split(r"[,，、/]\s*", raw)
    capabilities: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = part.strip().strip("\"'“”‘’")
        if not value or value in seen:
            continue
        if any(stop in value for stop in ("并", "然后", "加入")):
            value = re.split(r"并|然后|加入", value, maxsplit=1)[0].strip()
        if value:
            seen.add(value)
            capabilities.append(value)
    return capabilities


def _extract_allowed_tools(user_request: str) -> list[str] | None:
    match = re.search(
        r"(?:allowed_tools|工具白名单|允许工具|工具)\s*(?:设置为|为|是|=|:)\s*([^。；;\n]+)",
        user_request,
        re.I,
    )
    if not match:
        return None
    raw = match.group(1)
    parts = re.split(r"[,，、/]\s*", raw)
    tools: list[str] = []
    for part in parts:
        value = part.strip().strip("\"'“”‘’")
        if any(stop in value for stop in ("并", "然后", "加入")):
            value = re.split(r"并|然后|加入", value, maxsplit=1)[0].strip()
        if value:
            tools.append(value)
    return tools


def _should_add_custom_agent_to_conversation(user_request: str) -> bool:
    if "不加入" in user_request:
        return False
    return "加入" in user_request and ("群聊" in user_request or "当前" in user_request)


def _custom_agent_result_text(status: str, output: str | None) -> str:
    payload: Mapping[str, Any] = {}
    if output:
        try:
            parsed = json.loads(output)
            if isinstance(parsed, Mapping):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    if status == "ok":
        agent = payload.get("agent")
        if isinstance(agent, Mapping):
            capabilities = ", ".join(str(item) for item in agent.get("capabilities", []))
            allowed_tools = ", ".join(
                str(item) for item in agent.get("allowed_tools") or []
            )
            return (
                "已创建自建 Agent 并加入当前群聊。\n"
                f"- id: {agent.get('id')}\n"
                f"- name: {agent.get('name')}\n"
                f"- provider: {agent.get('provider')}\n"
                f"- capabilities: {capabilities}\n"
                f"- allowed_tools: {allowed_tools}"
            )
        return "已创建自建 Agent。"
    missing = payload.get("missing_fields")
    if isinstance(missing, list) and missing:
        return "创建自建 Agent 还缺少信息：" + ", ".join(str(item) for item in missing)
    error = payload.get("error") if isinstance(payload.get("error"), str) else None
    return f"创建自建 Agent 失败：{error or output or 'unknown error'}"
