"""Workspace-conflict task templates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.planning.routing import latest_user_request
from app.agents.orchestrator._internal.planning.templates.common import (
    available_orchestrator_agent_ids,
    preferred_agent,
)
from app.agents.orchestrator.artifacts import extract_artifact_paths_from_text
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage


def workspace_conflict_tasks_from_request(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[SubTask]:
    return derive_workspace_conflict_tasks(
        available_orchestrator_agent_ids(config),
        latest_user_request(messages),
    )


def derive_workspace_conflict_tasks(
    agent_ids: list[str],
    user_request: str,
) -> list[SubTask]:
    normalized = user_request.lower()
    if not (
        "workspace conflict" in normalized
        or "冲突处理" in user_request
        or "冲突文件" in user_request
        or "同一文件" in user_request
        or "同一个 run" in normalized
    ):
        return []
    if len(agent_ids) < 2:
        return []
    paths = extract_artifact_paths_from_text(user_request)
    target_path = paths[0] if paths else "shared-conflict.md"
    creator = preferred_agent(agent_ids, ("claude-code", "opencode-helper", "codex-helper"))
    first_modifier = preferred_agent(
        agent_ids,
        ("claude-code", "codex-helper", "opencode-helper"),
    )
    remaining = [agent_id for agent_id in agent_ids if agent_id != first_modifier]
    second_modifier = preferred_agent(
        remaining,
        ("opencode-helper", "codex-helper", "claude-code"),
    )
    if creator is None or first_modifier is None or second_modifier is None:
        return []
    return [
        SubTask(
            task_id="conflict-create",
            agent_id=creator,
            title=f"Create baseline {target_path}",
            instruction=(
                f"Create workspace file {target_path} with a short baseline section. "
                "Work only in the current workspace and do not create other files."
            ),
            priority=1,
            expected_output=target_path,
            include_history=False,
        ),
        SubTask(
            task_id="conflict-design",
            agent_id=first_modifier,
            title=f"Modify {target_path} from design perspective",
            instruction=(
                f"Modify the existing workspace file {target_path}. Add or replace "
                "content with the phrase 设计视角 and a concise design-oriented note. "
                "Do not create a new file."
            ),
            depends_on=("conflict-create",),
            priority=2,
            expected_output=target_path,
            include_history=False,
        ),
        SubTask(
            task_id="conflict-implementation",
            agent_id=second_modifier,
            title=f"Modify {target_path} from implementation perspective",
            instruction=(
                f"Modify the existing workspace file {target_path}. Add or replace "
                "content with the phrase 实现视角 and a concise implementation-oriented "
                "note. Do not create a new file."
            ),
            depends_on=("conflict-create",),
            priority=2,
            expected_output=target_path,
            include_history=False,
        ),
    ]
