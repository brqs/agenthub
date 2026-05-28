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
    "provide terminal commands for port previews."
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
            "sdk_options": {"permission_mode": "acceptEdits"},
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 180,
            "heartbeat_interval_seconds": 15,
        },
    },
    {
        "id": "codex-helper",
        "name": "Codex Helper",
        "provider": "codex",
        "avatar_url": "/avatars/openai.png",
        "capabilities": ["coding", "sandbox"],
        "system_prompt": (
            "You are Codex Helper, a code-focused agent runtime."
            f"{EXTERNAL_RUNTIME_PROMPT_SUFFIX}"
        ),
        "config": {
            "runtime": "cli",
            "sandbox_mode": "danger-full-access",
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 240,
            "heartbeat_interval_seconds": 15,
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
            "command": "opencode",
            "args": [],
            "max_runtime_seconds": 600,
            "idle_timeout_seconds": 180,
            "heartbeat_interval_seconds": 15,
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
            "and explain design rationale. When using write_file or read_file tools, pass "
            "a path argument with a workspace-relative path such as snake.html; do not use "
            "absolute paths or file_path for native AgentHub tools. Treat the latest user "
            "message as the only active request; earlier messages are context only. Create "
            "and edit files only. "
            "Do not run, suggest, output, or call tools for foreground or background "
            "preview/deploy servers or other long-running processes. If asked to preview or "
            "deploy on a port, create the files and state that AgentHub platform preview/deploy "
            "must be started outside the agent runtime."
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
