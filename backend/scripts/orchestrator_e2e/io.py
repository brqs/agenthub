"""Report, SSE, timestamp, and URL helpers."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class LineResponse(Protocol):
    def iter_lines(self) -> Any: ...


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def normalize_http_url(raw_url: Any) -> str | None:
    if not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    if not url:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        return url
    if url.startswith("//"):
        return f"http:{url}"
    return f"http://{url.lstrip('/')}"


def parse_sse(
    response: LineResponse,
    started_at: float,
    *,
    sse_path: Path,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_event = "message"
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal current_event, data_lines
        if current_event == "message" and not data_lines:
            return
        raw = "\n".join(data_lines)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"_raw": raw}
        event = {
            "ts": utc_now(),
            "elapsed_seconds": round(time.time() - started_at, 3),
            "event": current_event,
            "data": data,
        }
        events.append(event)
        append_jsonl(sse_path, event)
        current_event = "message"
        data_lines = []

    for line in response.iter_lines():
        if line == "":
            flush()
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
    flush()
    return events

