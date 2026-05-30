"""Runtime guard helpers shared by agent adapters."""

from __future__ import annotations

import re


def _prefixes(value: str) -> tuple[str, ...]:
    return tuple(value[:index] for index in range(1, len(value) + 1))


PREVIEW_DEPLOY_COMMAND_REPLACEMENT = (
    "Preview/deploy server commands are handled by AgentHub outside the agent runtime."
)

_PREVIEW_DEPLOY_COMMAND_PATTERNS = (
    re.compile(r"\bhttp\.server\b[^\n\r`;&|]*", re.I),
    re.compile(r"\b(?:python(?:3(?:\.\d+)?)?|py)\s+-m\s+http\.server\b[^\n\r`;&|]*", re.I),
    re.compile(r"\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:dev|preview|start)\b[^\n\r`;&|]*", re.I),
    re.compile(r"\bbun\s+(?:run\s+)?(?:dev|preview|start)\b[^\n\r`;&|]*", re.I),
    re.compile(r"\bnode\s+server\.js\b[^\n\r`;&|]*", re.I),
    re.compile(r"\b(?:npx\s+)?vite\b[^\n\r`;&|]*\s--host\b[^\n\r`;&|]*", re.I),
    re.compile(r"\b(?:npx\s+)?next\s+dev\b[^\n\r`;&|]*", re.I),
    re.compile(r"\b(?:npx\s+)?http-server\b[^\n\r`;&|]*", re.I),
    re.compile(r"\bapp\.listen\s*\([^`\n\r]*", re.I),
)
_POSSIBLE_PREVIEW_COMMAND_START = re.compile(
    r"(?i)(?:^|[\s`$>])("
    r"python(?:3(?:\.\d+)?)?|py|http(?:\.server|-server)?|"
    r"npm|pnpm|yarn|bun|npx|node|vite|next"
    r")\b"
)
_COMMAND_START_PREFIXES = frozenset(
    prefix
    for command in (
        "python",
        "python3",
        "py",
        "http.server",
        "http-server",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "npx",
        "node",
        "vite",
        "next",
    )
    for prefix in _prefixes(command)
)

_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b("
        r"OPENAI_API_KEY|ANTHROPIC_API_KEY|DEEPSEEK_API_KEY|"
        r"AGENTHUB_[A-Z0-9_]*TOKEN|[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET)"
        r")\s*=\s*([^\s'\"]+)"
    ),
    re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)([A-Za-z0-9._~+/=-]+)"),
    re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{12,})"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
)


def sanitize_preview_deploy_text(text: str) -> str:
    """Remove preview/deploy server command suggestions from user-visible text."""
    if not text:
        return text

    sanitized_lines = [
        _sanitize_preview_deploy_line(line) for line in text.splitlines(keepends=True)
    ]
    return "".join(sanitized_lines)


def redact_runtime_secrets(text: str) -> str:
    """Redact common API key/token forms from runtime diagnostics."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1[redacted]", redacted)
        else:
            redacted = pattern.sub("[redacted]", redacted)
    return redacted


class PreviewDeployTextFilter:
    """Streaming text filter that catches preview commands split across deltas."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""

        self._pending += text
        output: list[str] = []

        while True:
            newline_end = _first_newline_end(self._pending)
            if newline_end is None:
                break
            line = self._pending[:newline_end]
            self._pending = self._pending[newline_end:]
            output.append(sanitize_preview_deploy_text(line))

        if self._pending and not _should_hold_incomplete_line(self._pending):
            output.append(self._pending)
            self._pending = ""

        return "".join(output)

    def flush(self) -> str:
        output = sanitize_preview_deploy_text(self._pending)
        self._pending = ""
        return output


def _sanitize_preview_deploy_line(line: str) -> str:
    if not _contains_preview_deploy_command(line):
        return line

    newline = ""
    body = line
    if body.endswith("\r\n"):
        body = body[:-2]
        newline = "\r\n"
    elif body.endswith("\n"):
        body = body[:-1]
        newline = "\n"
    elif body.endswith("\r"):
        body = body[:-1]
        newline = "\r"

    indent = body[: len(body) - len(body.lstrip())]
    return f"{indent}{PREVIEW_DEPLOY_COMMAND_REPLACEMENT}{newline}"


def _contains_preview_deploy_command(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _PREVIEW_DEPLOY_COMMAND_PATTERNS)


def _should_hold_incomplete_line(line: str) -> bool:
    return _contains_possible_command_start(line) or _ends_with_command_start_prefix(line)


def _contains_possible_command_start(line: str) -> bool:
    return _POSSIBLE_PREVIEW_COMMAND_START.search(line) is not None


def _ends_with_command_start_prefix(line: str) -> bool:
    normalized = line.lower()
    tail = re.split(r"[\s`$>]", normalized)[-1]
    return tail in _COMMAND_START_PREFIXES


def _first_newline_end(text: str) -> int | None:
    lf = text.find("\n")
    cr = text.find("\r")
    indexes = [index for index in (lf, cr) if index >= 0]
    if not indexes:
        return None
    index = min(indexes)
    if text[index : index + 2] == "\r\n":
        return index + 2
    return index + 1
