"""Tests for context compression helpers."""

from __future__ import annotations

from app.services.context_compression import blocks_to_text


def test_blocks_to_text_flattens_tool_call_ok_block() -> None:
    text = blocks_to_text(
        [
            {
                "type": "tool_call",
                "call_id": "task-a.c-1",
                "tool_name": "write_file",
                "arguments": {"path": "snake.html", "content": "ignored"},
                "status": "ok",
                "output_preview": "wrote snake.html",
            }
        ]
    )

    assert "Tool call: write_file" in text
    assert "status=ok" in text
    assert "call_id=task-a.c-1" in text
    assert "paths=snake.html" in text
    assert "output=wrote snake.html" in text


def test_blocks_to_text_flattens_tool_call_pending_and_error_blocks() -> None:
    text = blocks_to_text(
        [
            {
                "type": "tool_call",
                "call_id": "c-pending",
                "tool_name": "read_file",
                "arguments": {"file_path": "src/App.tsx"},
                "status": "pending",
            },
            {
                "type": "tool_call",
                "call_id": "c-error",
                "tool_name": "bash",
                "arguments": {"command": "npm test"},
                "status": "error",
                "output_preview": "test failed",
            },
        ]
    )

    assert "status=pending" in text
    assert "paths=src/App.tsx" in text
    assert "status=error" in text
    assert "output=test failed" in text
