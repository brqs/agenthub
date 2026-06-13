"""Memory context construction, formatting, and injection."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import ChatMessage
from app.services._orchestrator_memory.capability_v1 import (
    build_agent_capability_profile,
    safe_failure_reason_summary,
)
from app.services._orchestrator_memory.capability_v2 import (
    build_agent_capability_profile_v2,
)
from app.services._orchestrator_memory.queries import (
    _conversation_user_id,
    _recent_terminal_runs,
)
from app.services._orchestrator_memory.run_reader import _format_run
from app.services._orchestrator_memory.serialization import (
    _format_counter,
    _truncate_preserving_edges,
)
from app.services._orchestrator_memory.types import (
    DEFAULT_AGENT_CAPABILITY_PROFILE_RECENT_RUNS,
    DEFAULT_AGENT_CAPABILITY_PROFILE_V2_RECENT_RUNS,
    DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS,
    DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS,
    MAX_AGENT_FAILURE_REASONS,
    AgentCapabilityProfileItem,
    AgentCapabilityProfileV2Item,
    UserPreferenceMemory,
)


async def build_orchestrator_memory_context(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    user_id: UUID | None = None,
    recent_runs: int = DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS,
    max_chars: int = DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS,
) -> ChatMessage | None:
    """Build a system message containing recent structured Orchestrator memory."""
    recent_runs = max(1, min(recent_runs, 10))
    max_chars = max(1, min(max_chars, 32000))
    runs = list(
        reversed(
            await _recent_terminal_runs(db, conversation_id, limit=recent_runs)
        )
    )

    sections: list[str] = []
    resolved_user_id = user_id or await _conversation_user_id(db, conversation_id)
    if resolved_user_id is not None:
        capability_profile_v2 = await build_agent_capability_profile_v2(
            db,
            resolved_user_id,
            conversation_id=conversation_id,
            recent_runs=DEFAULT_AGENT_CAPABILITY_PROFILE_V2_RECENT_RUNS,
        )
        profile_v2_section = _format_agent_capability_profile_v2(
            capability_profile_v2.items
        )
        if profile_v2_section:
            sections.append(profile_v2_section)
        preference_section = _format_user_preference_memory(
            capability_profile_v2.preferences
        )
        if preference_section:
            sections.append(preference_section)

    capability_profile = await build_agent_capability_profile(
        db,
        conversation_id,
        recent_runs=DEFAULT_AGENT_CAPABILITY_PROFILE_RECENT_RUNS,
    )
    profile_section = _format_agent_capability_profile(capability_profile)
    if profile_section:
        sections.append(profile_section)

    memory_lines: list[str] = ["Previous Orchestrator structured memory:", ""]
    for run in runs:
        formatted = await _format_run(db, run)
        if formatted:
            memory_lines.append(formatted)
    memory_section = "\n\n".join(memory_lines).strip()
    if memory_section != "Previous Orchestrator structured memory:":
        sections.append(memory_section)

    text = _truncate_preserving_edges("\n\n".join(sections).strip(), max_chars)
    if not text.strip():
        return None
    return ChatMessage(role="system", content=text)



def _format_agent_capability_profile_v2(
    items: list[AgentCapabilityProfileV2Item],
) -> str:
    if not items:
        return ""
    lines = ["Agent capability profile v2 from recent user Orchestrator runs:"]
    for item in items:
        parts = [
            f"scope={item.scope}",
            f"conversation_count={item.conversation_count}",
            f"task_count={item.task_count}",
            f"success_rate={item.success_rate}",
            f"weighted_task_count={item.weighted_task_count}",
            f"weighted_success_score={item.weighted_success_score}",
            f"weighted_failure_score={item.weighted_failure_score}",
            f"timeout_count={item.timeout_count}",
            f"repair_success_count={item.repair_success_count}",
            f"score={item.score}",
            f"confidence={item.confidence}",
        ]
        lines.append(f"- @{item.agent_id}: " + "; ".join(parts))
        if item.artifact_kinds:
            lines.append(f"  artifact_kinds: {_format_counter(item.artifact_kinds)}")
        if item.task_types:
            lines.append(f"  task_types: {_format_counter(item.task_types)}")
        if item.task_taxonomy:
            lines.append(f"  task_taxonomy: {_format_counter(item.task_taxonomy)}")
        if item.score_reasons:
            lines.append("  score_reasons: " + " | ".join(item.score_reasons))
        safe_reasons = [
            reason
            for reason in (
                safe_failure_reason_summary(reason)
                for reason in item.recent_failure_reasons
            )
            if reason
        ]
        if safe_reasons:
            lines.append(
                "  recent_failure_reasons: "
                + " | ".join(safe_reasons[:MAX_AGENT_FAILURE_REASONS])
            )
    return "\n".join(lines)



def _format_user_preference_memory(preferences: UserPreferenceMemory) -> str:
    if not preferences.runs_considered:
        return ""
    lines = [
        "User preference memory from recent Orchestrator runs:",
        (
            f"runs_considered={preferences.runs_considered}; "
            f"source_conversation_count={preferences.source_conversation_count}"
        ),
    ]
    if preferences.domains:
        lines.append(f"domains: {_format_counter(preferences.domains)}")
    if preferences.artifact_preferences:
        lines.append(
            f"artifact_preferences: {_format_counter(preferences.artifact_preferences)}"
        )
    if preferences.deployment_preferences:
        lines.append(
            f"deployment_preferences: {_format_counter(preferences.deployment_preferences)}"
        )
    if preferences.language_style_hints:
        lines.append(
            f"language_style_hints: {_format_counter(preferences.language_style_hints)}"
        )
    for summary_item in preferences.summary:
        lines.append(f"- {summary_item}")
    return "\n".join(lines)


def _format_agent_capability_profile(
    items: list[AgentCapabilityProfileItem],
) -> str:
    if not items:
        return ""
    lines = ["Agent capability profile from recent Orchestrator runs:"]
    for item in items:
        parts = [
            f"runs_considered={item.runs_considered}",
            f"task_count={item.task_count}",
            f"success_count={item.success_count}",
            f"failure_count={item.failure_count}",
            f"artifact_missing_count={item.artifact_missing_count}",
            f"evaluation_failed_count={item.evaluation_failed_count}",
            f"avg_attempts={item.avg_attempts}",
            f"repair_success_count={item.repair_success_count}",
            f"confidence={item.confidence}",
        ]
        lines.append(f"- @{item.agent_id}: " + "; ".join(parts))
        if item.artifact_kinds:
            lines.append(f"  artifact_kinds: {_format_counter(item.artifact_kinds)}")
        if item.review_outcomes:
            lines.append(f"  review_outcomes: {_format_counter(item.review_outcomes)}")
        safe_reasons = [
            reason
            for reason in (
                safe_failure_reason_summary(reason)
                for reason in item.recent_failure_reasons
            )
            if reason
        ]
        if safe_reasons:
            lines.append(
                "  recent_failure_reasons: "
                + " | ".join(safe_reasons[:MAX_AGENT_FAILURE_REASONS])
            )
    return "\n".join(lines)
def inject_orchestrator_memory_context(
    messages: list[ChatMessage],
    memory_message: ChatMessage | None,
) -> list[ChatMessage]:
    """Insert structured memory before the latest active user request."""
    if memory_message is None:
        return messages
    output = list(messages)
    for index in range(len(output) - 1, -1, -1):
        if output[index].role == "user":
            output.insert(index, memory_message)
            return output
    output.append(memory_message)
    return output
