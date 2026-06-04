"""Read-only HTTP server for an isolated workspace static snapshot."""

from __future__ import annotations

import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import settings

frame_ancestors = " ".join(
    ["'self'", *(item.strip() for item in settings.preview_allowed_frame_ancestors.split(","))]
)
HTML_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    f"frame-ancestors {frame_ancestors}"
)


class SnapshotRequestHandler(SimpleHTTPRequestHandler):
    """Serve files only; never generate directory listings."""

    server_version = "AgentHubStaticPreview/1.0"

    def __init__(self, *args: object, directory: str, entry_path: str, **kwargs: object) -> None:
        self._entry_path = entry_path
        super().__init__(*args, directory=directory, **kwargs)  # type: ignore[arg-type]

    def send_head(self):  # type: ignore[no-untyped-def]
        parsed_path = unquote(urlparse(self.path).path)
        if parsed_path in {"", "/"}:
            self.path = f"/{self._entry_path}"
        translated = Path(self.translate_path(self.path))
        root = Path(self.directory).resolve()
        resolved = translated.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError:
            self.send_error(404, "Static resource not found")
            return None
        if translated.is_dir():
            self.send_error(404, "Directory listing is disabled")
            return None
        return super().send_head()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.path.lower().split("?", 1)[0].endswith((".html", ".htm")):
            self.send_header("Content-Security-Policy", HTML_CSP)
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        _ = (format, args)


def main() -> None:
    """Run a snapshot server process."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    entry = (root / args.entry).resolve()
    entry.relative_to(root)
    if not entry.is_file():
        raise SystemExit("snapshot entry does not exist")

    def handler(*handler_args: object, **handler_kwargs: object) -> SnapshotRequestHandler:
        return SnapshotRequestHandler(
            *handler_args,
            directory=str(root),
            entry_path=args.entry,
            **handler_kwargs,
        )

    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)  # noqa: S104
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    os.umask(0o077)
    main()
