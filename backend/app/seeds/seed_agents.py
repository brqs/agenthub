"""
Seed built-in agents.

Usage:
    docker compose exec backend python -m app.seeds.seed_agents
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from app.agents.config_validation import validate_agent_config
from app.core.database import SessionFactory
from app.models.agent import Agent

BUILTIN_AGENTS: list[dict[str, Any]] = [
    {
        "id": "claude-code",
        "name": "Claude Code",
        "provider": "claude_code",
        "avatar_url": "/avatars/claude.png",
        "capabilities": ["coding", "files", "analysis"],
        "system_prompt": "You are Claude Code, a coding agent running inside the workspace.",
        "config": {"sdk_options": {"permission_mode": "acceptEdits"}},
    },
    {
        "id": "codex-helper",
        "name": "Codex Helper",
        "provider": "codex",
        "avatar_url": "/avatars/openai.png",
        "capabilities": ["coding", "sandbox"],
        "system_prompt": "You are Codex Helper, a code-focused agent runtime.",
        "config": {"timeout_seconds": 120},
    },
    {
        "id": "opencode-helper",
        "name": "OpenCode Helper",
        "provider": "opencode",
        "avatar_url": "/avatars/opencode.png",
        "capabilities": ["coding", "cli", "files"],
        "system_prompt": "You are OpenCode Helper, an OpenCode CLI-backed coding agent.",
        "config": {"command": "opencode", "args": [], "timeout_seconds": 120},
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
            "model_backend": "claude",
            "llm_planning": True,
            "direct_answer_on_planner_failure": True,
            "max_iterations": 10,
            "mcp_servers": [],
            "managed_agent_ids": [
                "claude-code",
                "codex-helper",
                "opencode-helper",
                "web-designer",
            ],
        },
    },
    {
        "id": "writer",
        "name": "Writer",
        "provider": "builtin",
        "avatar_url": "/avatars/writer.png",
        "capabilities": ["writing", "copywriting", "editing"],
        "system_prompt": (
            "You are a professional writer. Help users craft clear, engaging, "
            "and well-structured prose."
        ),
        "config": {
            "model_backend": "claude",
            "max_iterations": 10,
            "mcp_servers": [],
        },
    },
    {
        "id": "web-designer",
        "name": "Web Designer",
        "provider": "builtin",
        "avatar_url": "/avatars/web-designer.png",
        "capabilities": ["design", "html", "css"],
        "system_prompt": (
            "You are a senior web designer. Generate clean, modern HTML/CSS, suggest layouts, "
            "and explain design rationale."
        ),
        "config": {
            "model_backend": "claude",
            "max_iterations": 10,
            "mcp_servers": [],
        },
    },
]


async def seed() -> None:
    # Validate all built-in agents before touching the database
    for a in BUILTIN_AGENTS:
        validate_agent_config(
            provider=a["provider"],
            config=a["config"],
            system_prompt=a["system_prompt"],
        )

    async with SessionFactory() as db:
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
