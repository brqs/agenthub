"""Deterministic user preference memory extraction."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestrator_memory import OrchestratorRun
from app.services._orchestrator_memory.capability_v2 import _task_taxonomy
from app.services._orchestrator_memory.queries import _attempts_by_task, _tasks_for_runs
from app.services._orchestrator_memory.serialization import _format_counter
from app.services._orchestrator_memory.types import (
    MAX_USER_PREFERENCE_ITEMS,
    UserPreferenceMemory,
)
from app.services.artifacts.metadata import classify_artifact


async def _build_user_preference_memory(
    db: AsyncSession,
    runs: list[OrchestratorRun],
) -> UserPreferenceMemory:
    if not runs:
        return UserPreferenceMemory()
    run_ids = [run.id for run in runs]
    tasks = await _tasks_for_runs(db, run_ids)
    attempts_by_task = await _attempts_by_task(db, [task.id for task in tasks])

    domains: Counter[str] = Counter()
    artifact_preferences: Counter[str] = Counter()
    deployment_preferences: Counter[str] = Counter()
    language_style_hints: Counter[str] = Counter()

    for run in runs:
        text = f"{run.user_request}\n{run.final_summary}".lower()
        _count_keyword_preferences(domains, text, _DOMAIN_KEYWORDS)
        _count_keyword_preferences(deployment_preferences, text, _DEPLOYMENT_KEYWORDS)
        _count_keyword_preferences(language_style_hints, text, _LANGUAGE_STYLE_KEYWORDS)
    for task in tasks:
        for taxonomy in _task_taxonomy(task):
            domains.update([taxonomy])
        for attempt in attempts_by_task.get(task.id, []):
            for path in attempt.artifact_paths:
                artifact_preferences.update([classify_artifact(path)])
        if task.expected_output:
            artifact_preferences.update([classify_artifact(task.expected_output)])

    summary = _preference_summary(
        domains=domains,
        artifacts=artifact_preferences,
        deployments=deployment_preferences,
        language_style=language_style_hints,
    )
    return UserPreferenceMemory(
        runs_considered=len(runs),
        source_conversation_count=len({run.conversation_id for run in runs}),
        domains=dict(domains.most_common(MAX_USER_PREFERENCE_ITEMS)),
        artifact_preferences=dict(artifact_preferences.most_common(MAX_USER_PREFERENCE_ITEMS)),
        deployment_preferences=dict(deployment_preferences.most_common(MAX_USER_PREFERENCE_ITEMS)),
        language_style_hints=dict(language_style_hints.most_common(MAX_USER_PREFERENCE_ITEMS)),
        summary=summary,
    )


_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "frontend": ("frontend", "前端", "网页", "html", "css", "移动端"),
    "backend": ("backend", "后端", "api", "fastapi", "pytest"),
    "document": ("document", "markdown", "文档", "报告", "说明"),
    "workflow": ("workflow", "工作流"),
    "deployment": ("deploy", "部署", "preview", "预览", "公网"),
    "evaluation": ("evaluation", "验收", "review", "修复", "repair"),
}
_DEPLOYMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "preview": ("preview", "预览"),
    "public_deploy": ("public", "公网", "部署"),
    "port_8082": ("8082", "port 8082", "端口8082"),
    "health_check": ("health", "健康", "验活"),
}
_LANGUAGE_STYLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "chinese": ("中文", "汉语"),
    "concise": ("简洁", "精简", "concise"),
    "detailed": ("详细", "完整", "详尽"),
    "mobile_responsive": ("移动端", "响应式", "mobile"),
}


def _count_keyword_preferences(
    counter: Counter[str],
    text: str,
    keyword_map: Mapping[str, tuple[str, ...]],
) -> None:
    for name, markers in keyword_map.items():
        if any(marker in text for marker in markers):
            counter.update([name])


def _preference_summary(
    *,
    domains: Counter[str],
    artifacts: Counter[str],
    deployments: Counter[str],
    language_style: Counter[str],
) -> list[str]:
    summary: list[str] = []
    if domains:
        summary.append("frequent_domains: " + _format_counter(dict(domains.most_common(3))))
    if artifacts:
        summary.append("artifact_preferences: " + _format_counter(dict(artifacts.most_common(3))))
    if deployments:
        summary.append(
            "deployment_preferences: "
            + _format_counter(dict(deployments.most_common(3)))
        )
    if language_style:
        summary.append(
            "language_style_hints: "
            + _format_counter(dict(language_style.most_common(3)))
        )
    return summary[:4]
