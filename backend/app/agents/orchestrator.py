"""Orchestrator injection-based sub-agent dispatch."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from app.agents.base import BaseAgentAdapter
from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator_planner import llm_planning_enabled, plan_task_payload
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

AdapterFactory = Callable[[str], BaseAgentAdapter | Awaitable[BaseAgentAdapter]]
DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS = 4000
DEFAULT_TASK_RESULT_ITEM_MAX_CHARS = 1200
DEFAULT_MAX_TASK_ATTEMPTS = 1
MAX_TASK_ATTEMPTS_LIMIT = 3
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
GROUP_AGENT_QUESTION_MARKERS = (
    "当前群聊有哪些agent",
    "当前群聊有哪些成员",
    "当前群聊里有哪些agent",
    "当前群里有哪些agent",
    "当前群聊有什么agent",
    "当前群里有什么agent",
    "当前群聊里有谁",
    "当前群里有谁",
    "群聊有哪些agent",
    "群聊有什么agent",
    "群聊里有谁",
    "群聊成员",
    "群里有哪些agent",
    "群里有哪些成员",
    "群里有什么agent",
    "群里有谁",
    "agents in group",
    "agents are in this group",
    "who is in this group",
    "current group agents",
    "group agents",
)
PLATFORM_FACT_TYPES = {
    "group_agents",
    "group_models",
    "group_capabilities",
    "self_model",
}
MODEL_FACT_MARKERS = (
    "模型",
    "model",
    "models",
    "runtime",
    "后端",
    "backend",
)
GROUP_FACT_MARKERS = (
    "当前群聊",
    "当前群里",
    "这个群聊",
    "本群",
    "群里",
    "群聊",
    "group",
)
CAPABILITY_FACT_MARKERS = (
    "能做什么",
    "可以做什么",
    "能力",
    "capabilities",
    "capability",
    "what can",
)
SELF_FACT_MARKERS = (
    "你是什么模型",
    "你用什么模型",
    "你使用什么模型",
    "你是什么后端",
    "你用什么后端",
    "你是什么runtime",
    "what model are you",
    "which model are you",
    "what backend are you",
    "which backend are you using",
    "what runtime are you",
)
MODEL_FOLLOWUP_MARKERS = (
    "还有哪些模型",
    "还有什么模型",
    "还有哪些",
    "还有什么",
    "what other models",
    "which other models",
    "any other models",
)
PLATFORM_FACT_CLASSIFIER_PROMPT = """Classify whether the user's latest message asks
for an AgentHub platform fact. Return strict JSON only:
{"intent":"platform_fact"|"other","fact_type":"group_agents"|"group_models"|"group_capabilities"|"self_model"|null,"confidence":0.0}
Do not answer the user. Do not include markdown.
"""

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


class TaskState(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ARTIFACT_MISSING = "artifact_missing"


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
class TaskAttempt:
    attempt_index: int
    agent_id: str
    state: TaskState = TaskState.PENDING
    text_preview: str = ""
    tool_summaries: list[str] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    missing_artifact_paths: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class TaskResult:
    task_id: str
    title: str
    final_state: TaskState = TaskState.PENDING
    attempts: list[TaskAttempt] = field(default_factory=list)


@dataclass(slots=True)
class OrchestratorRunContext:
    results: dict[str, TaskResult] = field(default_factory=dict)
    result_order: list[str] = field(default_factory=list)

    def record(self, result: TaskResult) -> None:
        if result.task_id not in self.results:
            self.result_order.append(result.task_id)
        self.results[result.task_id] = result


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
        platform_fact = await _platform_fact_intent(merged_config, messages)
        if platform_fact:
            for chunk in _text_block(
                next_block_index,
                _platform_fact_text(merged_config, platform_fact),
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

        for chunk in _text_block(next_block_index, _planning_text(tasks)):
            yield chunk
        next_block_index += 1

        task_states = {task.task_id: TaskState.PENDING for task in tasks}
        run_context = OrchestratorRunContext()
        for task in tasks:
            if not _dependencies_satisfied(task, task_states):
                task_states[task.task_id] = TaskState.SKIPPED
                run_context.record(
                    TaskResult(
                        task_id=task.task_id,
                        title=task.title,
                        final_state=TaskState.SKIPPED,
                    )
                )
                continue

            async for chunk, updated_block_index in _run_task(
                merged_config,
                task,
                messages,
                next_block_index,
                run_context,
                workspace_path,
                tool_specs,
            ):
                next_block_index = updated_block_index
                yield chunk
            task_states[task.task_id] = run_context.results[task.task_id].final_state

        for chunk in _text_block(
            next_block_index,
            _summary_text(tasks, task_states, run_context),
        ):
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


async def _platform_fact_intent(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[str]:
    intent = _rule_platform_fact_intent(config, messages)
    if intent:
        return intent
    if config.get("platform_fact_classifier_enabled") is True:
        return await _classify_platform_fact_intent(config, messages)
    return []


def _rule_platform_fact_intent(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[str]:
    user_request = _latest_user_request(messages)
    normalized = _strip_orchestrator_mention(user_request).lower()
    compact = _compact_text(normalized)
    has_conversation_agents = bool(_conversation_agents(config))
    agent_ids = _agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
    explicit_mentions = _explicit_agent_mentions(agent_ids, user_request)

    if len(explicit_mentions) >= 2 or (explicit_mentions and _has_task_intent(normalized)):
        return []

    intents: list[str] = []
    if has_conversation_agents and _is_group_agent_question(normalized, compact):
        intents.append("group_agents")
    if has_conversation_agents and _is_group_capability_question(normalized, compact):
        intents.append("group_capabilities")
    if has_conversation_agents and _matches_model_followup(messages):
        intents.append("group_models")
    if has_conversation_agents and _is_group_model_question(normalized, compact):
        intents.append("group_models")
    if _is_self_model_question(normalized, compact):
        intents.append("self_model")
    return _dedupe_intents(intents)


def _is_group_agent_question(normalized: str, compact: str) -> bool:
    return _matches_any(normalized, compact, GROUP_AGENT_QUESTION_MARKERS)


def _is_group_model_question(normalized: str, compact: str) -> bool:
    group_model_phrases = (
        "当前群聊有哪些模型",
        "当前群里有哪些模型",
        "这个群聊有哪些模型",
        "本群有哪些模型",
        "群聊有哪些模型",
        "群里有哪些模型",
        "当前群聊支持什么模型",
        "当前群里支持什么模型",
        "这个群聊支持什么模型",
        "本群支持什么模型",
        "群聊支持什么模型",
        "群里支持什么模型",
        "当前群聊支持哪些模型",
        "群聊支持哪些模型",
        "群里支持哪些模型",
        "models in group",
        "group models",
        "available models",
    )
    if _matches_any(normalized, compact, group_model_phrases):
        return True
    return any(
        marker in normalized or marker in compact
        for marker in (
            "当前有哪些模型",
            "有哪些模型",
        )
    )


def _is_self_model_question(normalized: str, compact: str) -> bool:
    if _matches_any(normalized, compact, SELF_FACT_MARKERS):
        return True
    self_markers = ("你", "orchestrator", "you", "your")
    has_self = any(marker in normalized or marker in compact for marker in self_markers)
    has_model = any(marker in normalized or marker in compact for marker in MODEL_FACT_MARKERS)
    return has_self and has_model


def _is_group_capability_question(normalized: str, compact: str) -> bool:
    has_capability = any(
        marker in normalized or marker in compact for marker in CAPABILITY_FACT_MARKERS
    )
    has_group_or_agents = any(
        marker in normalized or marker in compact
        for marker in (*GROUP_FACT_MARKERS, "agent", "agents", "成员")
    )
    return has_capability and has_group_or_agents


def _dedupe_intents(intents: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for intent in intents:
        if intent not in PLATFORM_FACT_TYPES or intent in seen:
            continue
        seen.add(intent)
        result.append(intent)
    return result


def _matches_model_followup(messages: list[ChatMessage]) -> bool:
    latest = _strip_orchestrator_mention(_latest_user_request(messages)).lower()
    latest_compact = _compact_text(latest)
    if not _matches_any(latest, latest_compact, MODEL_FOLLOWUP_MARKERS):
        return False
    return any(
        any(marker in previous for marker in MODEL_FACT_MARKERS)
        for previous in _recent_user_messages_before_latest(messages)
    )


def _recent_user_messages_before_latest(messages: list[ChatMessage]) -> list[str]:
    previous: list[str] = []
    found_latest = False
    for message in reversed(messages):
        if message.role != "user" or not message.content.strip():
            continue
        if not found_latest:
            found_latest = True
            continue
        previous.append(_strip_orchestrator_mention(message.content).lower())
        if len(previous) >= 3:
            break
    return previous


def _matches_any(normalized: str, compact: str, markers: tuple[str, ...]) -> bool:
    return any(
        marker in normalized or marker in compact
        for marker in markers
    )


def _conversation_agents(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = config.get("conversation_agents")
    if not isinstance(value, list):
        return []
    agents: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        agent_id = item.get("id")
        name = item.get("name")
        if not isinstance(agent_id, str) or not agent_id.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        agents.append(item)
    return agents


async def _classify_platform_fact_intent(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[str]:
    try:
        text = await _collect_platform_fact_classifier_text(config, messages)
    except Exception:  # noqa: BLE001
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, Mapping):
        return []
    intent = payload.get("intent")
    fact_type = payload.get("fact_type")
    confidence = payload.get("confidence")
    if intent != "platform_fact":
        return []
    if fact_type not in PLATFORM_FACT_TYPES:
        return []
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return []
    if confidence < 0.65:
        return []
    if fact_type != "self_model" and not _conversation_agents(config):
        return []
    return [str(fact_type)]


async def _collect_platform_fact_classifier_text(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> str:
    gateway = _platform_fact_classifier_gateway(config)
    parts: list[str] = []
    async for chunk in gateway.stream(
        _platform_fact_classifier_messages(messages),
        system_prompt=PLATFORM_FACT_CLASSIFIER_PROMPT,
        config=_platform_fact_classifier_config(config),
    ):
        if chunk.event_type == "delta":
            parts.append(chunk.text_delta or chunk.code_delta or "")
        elif chunk.event_type == "error":
            raise ValueError(_error_reason(chunk))
    return "".join(parts).strip()


def _platform_fact_classifier_gateway(config: Mapping[str, Any]) -> Any:
    gateway = config.get("platform_fact_classifier_gateway")
    if gateway is not None:
        return gateway

    backend = config.get(
        "platform_fact_classifier_model_backend",
        config.get("answer_model_backend", config.get("model_backend", "claude")),
    )
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("invalid_platform_fact_classifier: backend must be a string")
    return ModelGateway(
        backend,
        default_config=_platform_fact_classifier_config(config),
        agent_id="orchestrator-platform-fact-classifier",
        system_prompt=PLATFORM_FACT_CLASSIFIER_PROMPT,
    )


def _platform_fact_classifier_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw_config = config.get("platform_fact_classifier_config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ValueError(
            "invalid_platform_fact_classifier: platform_fact_classifier_config must be an object"
        )
    classifier_config: dict[str, Any] = {
        "temperature": 0,
        "max_tokens": 128,
    }
    classifier_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in classifier_config:
            classifier_config[key] = config[key]
    return classifier_config


def _platform_fact_classifier_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    recent = [
        f"{message.role}: {message.content}"
        for message in messages[-6:]
        if message.role in {"user", "assistant"} and message.content.strip()
    ]
    return [
        ChatMessage(
            role="user",
            content="Recent messages:\n" + "\n".join(recent),
        )
    ]


def _platform_fact_text(config: Mapping[str, Any], fact_types: list[str]) -> str:
    sections: list[str] = []
    for fact_type in fact_types:
        if fact_type == "group_agents":
            sections.append(_group_agents_text(config).strip())
        elif fact_type == "group_models":
            sections.append(_group_models_text(config).strip())
        elif fact_type == "group_capabilities":
            sections.append(_group_capabilities_text(config).strip())
        elif fact_type == "self_model":
            sections.append(_self_model_text(config).strip())
    return "\n\n".join(section for section in sections if section) + "\n"


def _group_agents_text(config: Mapping[str, Any]) -> str:
    agents = _conversation_agents(config)
    lines = [f"当前群聊包含 {len(agents)} 个 agent：", ""]
    for agent in agents:
        agent_id = str(agent["id"])
        name = str(agent["name"])
        provider = agent.get("provider")
        capabilities = agent.get("capabilities")
        detail_parts = [f"id: {agent_id}"]
        if isinstance(provider, str) and provider:
            detail_parts.append(f"provider: {provider}")
        line = f"- {name} ({', '.join(detail_parts)})"
        if isinstance(capabilities, list):
            capability_names = [
                item for item in capabilities if isinstance(item, str) and item.strip()
            ]
            if capability_names:
                line += f" - capabilities: {', '.join(capability_names)}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _group_models_text(config: Mapping[str, Any]) -> str:
    agents = _conversation_agents(config)
    lines = [f"当前群聊包含 {len(agents)} 个 agent；可见的模型/运行时配置如下：", ""]
    for agent in agents:
        name = str(agent["name"])
        agent_id = str(agent["id"])
        details = _agent_model_details(agent)
        lines.append(f"- {name} (id: {agent_id}): {details}")
    return "\n".join(lines) + "\n"


def _agent_model_details(agent: Mapping[str, Any]) -> str:
    provider = _safe_str(agent.get("provider"))
    parts: list[str] = []
    if provider:
        parts.append(f"provider: {provider}")
    for label, key in (
        ("runtime", "runtime"),
        ("model_backend", "model_backend"),
        ("answer_model_backend", "answer_model_backend"),
        ("planner_model_backend", "planner_model_backend"),
        ("qa_model_backend", "qa_model_backend"),
        ("qa_model", "qa_model"),
    ):
        value = _safe_str(agent.get(key))
        if value:
            parts.append(f"{label}: {value}")
    if _safe_str(agent.get("id")) == "orchestrator":
        if not _safe_str(agent.get("answer_model_backend")) and not _safe_str(
            agent.get("model_backend")
        ):
            parts.append("direct answer backend: 未在 AgentHub 配置中暴露")
        if not _safe_str(agent.get("planner_model_backend")) and not _safe_str(
            agent.get("model_backend")
        ):
            parts.append("planner backend: 未在 AgentHub 配置中暴露")
    elif not any(_safe_str(agent.get(key)) for key in _model_detail_keys()):
        parts.append("执行模型: 未在 AgentHub 配置中暴露")
    return "; ".join(parts) if parts else "未在 AgentHub 配置中暴露"


def _group_capabilities_text(config: Mapping[str, Any]) -> str:
    agents = _conversation_agents(config)
    lines = [f"当前群聊包含 {len(agents)} 个 agent；能力配置如下：", ""]
    for agent in agents:
        capabilities = agent.get("capabilities")
        caps = []
        if isinstance(capabilities, list):
            caps = [item for item in capabilities if isinstance(item, str) and item.strip()]
        summary = ", ".join(caps) if caps else "未在 AgentHub 配置中暴露"
        lines.append(f"- {agent['name']} (id: {agent['id']}): {summary}")
    return "\n".join(lines) + "\n"


def _self_model_text(config: Mapping[str, Any]) -> str:
    answer_backend = _config_backend(config, "answer_model_backend")
    planner_backend = _config_backend(config, "planner_model_backend")
    lines = [
        "我是 AgentHub Orchestrator。",
        f"- direct answer backend: {answer_backend}",
        f"- planner backend: {planner_backend}",
    ]
    exact_model = _safe_str(config.get("model"))
    if exact_model:
        lines.append(f"- model: {exact_model}")
    else:
        lines.append("- model: 未在 AgentHub 配置中暴露")
    return "\n".join(lines) + "\n"


def _config_backend(config: Mapping[str, Any], key: str) -> str:
    value = _safe_str(config.get(key))
    if value:
        return value
    fallback = _safe_str(config.get("model_backend"))
    if fallback:
        return fallback
    return "未在 AgentHub 配置中暴露"


def _model_detail_keys() -> tuple[str, ...]:
    return (
        "runtime",
        "model_backend",
        "answer_model_backend",
        "planner_model_backend",
        "qa_model_backend",
        "qa_model",
    )


def _safe_str(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


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
                _attempt_call_id_prefix(task.task_id, attempt_index),
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


def _attempt_call_id_prefix(task_id: str, attempt_index: int) -> str:
    if attempt_index == 1:
        return task_id
    return f"{task_id}.attempt-{attempt_index}"


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
