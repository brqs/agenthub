"""Prompt helpers for external agent runtimes."""

from __future__ import annotations

from pathlib import Path


def workspace_guard_prompt(workspace_path: Path) -> str:
    """Return runtime-agnostic workspace rules for external coding agents."""
    return "\n".join(
        [
            "AgentHub workspace rules:",
            f"- Workspace root: {workspace_path}",
            "- Create, edit, read, and reference project files only inside the "
            "workspace root. Prefer relative paths from the workspace root.",
            "- Never write to /home/user, /home/ubuntu, /tmp, parent directories, "
            "or any absolute path outside the workspace root.",
            "- Do not start long-running or background servers or processes. Do not "
            "use background '&', nohup, disown, python -m http.server, npm run dev, "
            "vite dev, next dev, or similar preview servers unless the user explicitly "
            "asks and AgentHub exposes that command.",
            "- For web apps, write the files in the workspace and tell the user which "
            "files changed; preview is handled by AgentHub Workspace.",
        ]
    )
