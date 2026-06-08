"""
Seed built-in agents.

Usage:
    docker compose exec backend python -m app.seeds.seed_agents
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from app.agents.config_fields import (
    EXTERNAL_DIRECT_CHAT_DEFAULTS,
    ORCHESTRATOR_DEFAULTS,
)
from app.agents.config_validation import validate_agent_config
from app.core.database import SessionFactory
from app.models.agent import Agent

EXTERNAL_RUNTIME_PROMPT_SUFFIX = (
    " Work only inside the AgentHub workspace. Treat the latest user message as the "
    "only active request; earlier messages are context only, and you must not "
    "continue previous coding tasks unless the latest user message explicitly asks "
    "you to. If the latest user message asks what you are, which model or agent you "
    "are, your status, or asks for an explanation, answer directly in text without "
    "inspecting files or calling tools unless that message asks you to. Create or "
    "edit files. Do not run, suggest, or output shell commands for foreground or "
    "background preview/deploy servers or other long-running processes. Do not include "
    "preview/deploy server commands in final text, even to say you will not run them. "
    "If the user "
    "asks to deploy or preview on a port, generate the files and state that AgentHub "
    "platform preview/deploy must be started outside the agent runtime. Do not "
    "provide terminal commands for port previews. Do not create server.js, "
    "package.json start/dev/preview scripts, Express/Node/Vite/Next server files, "
    "or server dependencies merely to expose a preview port."
)

CODEX_PLANNING_PROFILE = (
    "适合复杂 AgentHub 代码任务的方案拆解、总体规划、仓库理解、"
    "架构判断和任务验收；负责审阅其他 agent 完成并测试后的代码；"
    "当其他 agent 无法解决复杂 bug 或需要求助时接手处理；作为多 agent "
    "工作流的总负责人和技术兜底者。除非任务需要最高复杂度判断或兜底修复，"
    "否则不要把普通并行实现任务全部交给它。"
)
CLAUDE_CODE_PLANNING_PROFILE = (
    "适合承担明确子任务的代码实现、文件编辑、功能补全、bug 修复和代码审阅；"
    "在并行开发场景中应与 OpenCode 同时承担不同实现任务；适合把 Codex "
    "拆好的方案落地为代码。"
)
OPENCODE_PLANNING_PROFILE = (
    "适合 OpenCode CLI 驱动的代码实现、文件修改、补充开发、独立验证和修复；"
    "在并行开发场景中应与 Claude Code 同时承担不同实现任务；"
    "适合作为第二实现者或验证修复者。"
)

BUILTIN_AGENTS: list[dict[str, Any]] = [
    {
        "id": "claude-code",
        "name": "Claude Code",
        "provider": "claude_code",
        "avatar_url": "/avatars/claude.png",
        "capabilities": ["coding", "files", "analysis"],
        "system_prompt": (
            "You are Claude Code, a coding agent running inside the workspace."
            f"{EXTERNAL_RUNTIME_PROMPT_SUFFIX}"
        ),
        "config": {
            "planning_profile": CLAUDE_CODE_PLANNING_PROFILE,
            "planning_strengths": [
                "file_editing",
                "implementation",
                "code_generation",
                "debugging",
                "code_review",
                "workspace_changes",
                "parallel_implementation",
            ],
            "planning_weaknesses": [
                "global_architecture_ownership",
                "unresolved_complex_escalations",
            ],
            "preferred_task_types": ["implementation", "repair", "review"],
            "sdk_options": {"permission_mode": "acceptEdits"},
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 180,
            "heartbeat_interval_seconds": 15,
            **EXTERNAL_DIRECT_CHAT_DEFAULTS,
        },
    },
    {
        "id": "codex-helper",
        "name": "Codex Helper",
        "provider": "codex",
        "avatar_url": "/avatars/openai.png",
        "capabilities": ["coding", "sandbox"],
        "system_prompt": (
            "You are Codex Helper, the lead designer and chief architect for complex "
            "AgentHub coding tasks. When Orchestrator assigns architecture work, produce "
            "clear execution plans, file ownership, acceptance criteria, and risk notes "
            "before implementation is delegated. For direct implementation tasks, act as "
            "a code-focused agent runtime."
            f"{EXTERNAL_RUNTIME_PROMPT_SUFFIX}"
        ),
        "config": {
            "planning_profile": CODEX_PLANNING_PROFILE,
            "planning_strengths": [
                "architecture",
                "repo_analysis",
                "task_planning",
                "final_review",
                "difficult_bug_fixing",
                "escalation_owner",
                "technical_lead",
            ],
            "planning_weaknesses": [
                "routine_parallel_implementation",
                "simple_file_edits",
            ],
            "preferred_task_types": [
                "planning",
                "architecture",
                "review",
                "repair",
                "escalation",
            ],
            "runtime": "cli",
            "sandbox_mode": "danger-full-access",
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 240,
            "heartbeat_interval_seconds": 15,
            **EXTERNAL_DIRECT_CHAT_DEFAULTS,
        },
    },
    {
        "id": "opencode-helper",
        "name": "OpenCode Helper",
        "provider": "opencode",
        "avatar_url": "/avatars/opencode.png",
        "capabilities": ["coding", "cli", "files"],
        "system_prompt": (
            "You are OpenCode Helper, an OpenCode CLI-backed coding agent."
            f"{EXTERNAL_RUNTIME_PROMPT_SUFFIX}"
        ),
        "config": {
            "planning_profile": OPENCODE_PLANNING_PROFILE,
            "planning_strengths": [
                "cli_workflow",
                "implementation",
                "file_editing",
                "verification",
                "repair",
                "parallel_execution",
                "parallel_implementation",
            ],
            "planning_weaknesses": [
                "global_architecture_ownership",
                "final_technical_arbitration",
            ],
            "preferred_task_types": ["implementation", "verification", "repair"],
            "command": "opencode",
            "args": [],
            "model": "deepseek/deepseek-chat",
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 360,
            "heartbeat_interval_seconds": 15,
            **EXTERNAL_DIRECT_CHAT_DEFAULTS,
        },
    },
    {
        "id": "orchestrator",
        "name": "Orchestrator",
        "provider": "builtin",
        "avatar_url": "/avatars/orchestrator.png",
        "capabilities": ["task_decomposition", "coordination"],
        "system_prompt": (
            "You are an Orchestrator agent. Answer simple identity, model, and capability "
            "questions directly. For complex task requests, decompose the work into "
            "sub-tasks and dispatch each to the most suitable specialist agent."
        ),
        "config": {
            **ORCHESTRATOR_DEFAULTS,
            "mcp_servers": [],
            "managed_agent_ids": [
                "claude-code",
                "codex-helper",
                "opencode-helper",
            ],
        },
    },
]

ACTIVE_BUILTIN_AGENT_IDS = {agent["id"] for agent in BUILTIN_AGENTS}


async def seed() -> None:
    # Validate all built-in agents before touching the database
    for a in BUILTIN_AGENTS:
        validate_agent_config(
            provider=a["provider"],
            config=a["config"],
            system_prompt=a["system_prompt"],
        )

    async with SessionFactory() as db:
        stale_builtins = (
            await db.execute(select(Agent).where(Agent.is_builtin.is_(True)))
        ).scalars()
        for stale in stale_builtins:
            if stale.id not in ACTIVE_BUILTIN_AGENT_IDS:
                await db.delete(stale)
                print(f"  deleted stale builtin {stale.id}")
        for a in BUILTIN_AGENTS:
            exists = (
                await db.execute(select(Agent).where(Agent.id == a["id"]))
            ).scalar_one_or_none()
            if exists:
                exists.user_id = None
                exists.name = a["name"]
                exists.provider = a["provider"]
                exists.avatar_url = a["avatar_url"]
                exists.capabilities = a["capabilities"]
                exists.system_prompt = a["system_prompt"]
                exists.config = a["config"]
                exists.is_builtin = True
                print(f"  updated {a['id']}")
                continue
            db.add(Agent(is_builtin=True, **a))
            print(f"  inserted {a['id']}")
        await db.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
