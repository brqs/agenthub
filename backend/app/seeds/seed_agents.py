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
        "provider": "claude",
        "avatar_url": "/avatars/claude.png",
        "capabilities": ["coding", "writing", "analysis"],
        "system_prompt": None,
        "config": {"model": "claude-sonnet-4-6", "temperature": 0.7, "max_tokens": 4096},
    },
    {
        "id": "codex-helper",
        "name": "Codex Helper",
        "provider": "openai",
        "avatar_url": "/avatars/openai.png",
        "capabilities": ["coding"],
        "system_prompt": None,
        "config": {"model": "gpt-4o", "temperature": 0.7, "max_tokens": 4096},
    },
    {
        "id": "orchestrator",
        "name": "Orchestrator",
        "provider": "custom",
        "avatar_url": "/avatars/orchestrator.png",
        "capabilities": ["task_decomposition", "coordination"],
        "system_prompt": (
            "You are an Orchestrator agent. Given a user's complex request, decompose it "
            "into sub-tasks and dispatch each to the most suitable specialist agent. "
            "Return a structured task plan."
        ),
        "config": {
            "model": "claude-sonnet-4-6",
            "upstream_provider": "claude",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
    },
    {
        "id": "writer",
        "name": "Writer",
        "provider": "custom",
        "avatar_url": "/avatars/writer.png",
        "capabilities": ["writing", "copywriting", "editing"],
        "system_prompt": (
            "You are a professional writer. Help users craft clear, engaging, "
            "and well-structured prose."
        ),
        "config": {
            "model": "claude-sonnet-4-6",
            "upstream_provider": "claude",
            "temperature": 0.8,
            "max_tokens": 4096,
        },
    },
    {
        "id": "web-designer",
        "name": "Web Designer",
        "provider": "custom",
        "avatar_url": "/avatars/web-designer.png",
        "capabilities": ["design", "html", "css"],
        "system_prompt": (
            "You are a senior web designer. Generate clean, modern HTML/CSS, suggest layouts, "
            "and explain design rationale."
        ),
        "config": {
            "model": "claude-sonnet-4-6",
            "upstream_provider": "claude",
            "temperature": 0.7,
            "max_tokens": 4096,
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
                print(f"  → skip {a['id']} (already exists)")
                continue
            db.add(Agent(is_builtin=True, **a))
            print(f"  ✓ inserted {a['id']}")
        await db.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
