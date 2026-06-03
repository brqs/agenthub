"""Tests for StreamingArtifactParser."""

from __future__ import annotations

from app.agents.artifact_parser import StreamingArtifactParser


def _all_chunks(parser: StreamingArtifactParser, *feeds: str) -> list:
    """Feed texts and flush, collecting every chunk."""
    chunks = []
    for text in feeds:
        chunks.extend(parser.feed(text))
    chunks.extend(parser.flush())
    return chunks


def _extract_blocks(chunks: list) -> list[dict]:
    """Aggregate sequential chunks into block dicts for easy assertion."""
    blocks: list[dict] = []
    current: dict | None = None
    for c in chunks:
        if c.event_type == "block_start":
            current = {
                "index": c.block_index,
                "type": c.block_type,
                "metadata": c.metadata or {},
                "text": "",
                "code": "",
            }
        elif c.event_type == "delta" and current is not None:
            if c.text_delta:
                current["text"] += c.text_delta
            if c.code_delta:
                current["code"] += c.code_delta
        elif c.event_type == "block_end" and current is not None:
            blocks.append(current)
            current = None
    return blocks


class TestStreamingArtifactParser:
    def test_plain_text(self) -> None:
        parser = StreamingArtifactParser()
        chunks = []
        chunks.extend(parser.feed("hello world"))
        chunks.extend(parser.flush())

        assert [c.event_type for c in chunks] == ["block_start", "delta", "block_end"]
        assert chunks[0].block_index == 0
        assert chunks[0].block_type == "text"
        assert chunks[1].text_delta == "hello world"
        assert chunks[2].block_index == 0

    def test_single_code_block(self) -> None:
        parser = StreamingArtifactParser()
        text = "before\n```python\nprint(1)\n```\nafter"
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 3
        assert blocks[0]["type"] == "text"
        assert "before" in blocks[0]["text"]
        assert blocks[1]["type"] == "code"
        assert blocks[1]["metadata"].get("language") == "python"
        assert "print(1)" in blocks[1]["code"]
        assert blocks[2]["type"] == "text"
        assert "after" in blocks[2]["text"]

    def test_fence_split_across_chunks(self) -> None:
        parser = StreamingArtifactParser()
        chunks = []
        chunks.extend(parser.feed("hello\n``"))
        chunks.extend(parser.feed("`python\nprint(1)\n"))
        chunks.extend(parser.feed("``"))
        chunks.extend(parser.feed("`\nworld"))
        chunks.extend(parser.flush())

        # Ensure no triple-backtick leaks into any delta.
        for c in chunks:
            if c.event_type == "delta":
                assert "```" not in (c.text_delta or "")
                assert "```" not in (c.code_delta or "")

        blocks = _extract_blocks(chunks)
        assert len(blocks) == 3
        assert blocks[0]["type"] == "text"
        assert "hello" in blocks[0]["text"]
        assert blocks[1]["type"] == "code"
        assert "print(1)" in blocks[1]["code"]
        assert blocks[2]["type"] == "text"
        assert "world" in blocks[2]["text"]

    def test_multiple_code_blocks(self) -> None:
        parser = StreamingArtifactParser()
        text = "t1\n```python\nc1\n```\nt2\n```tsx\nc2\n```\nt3"
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 5
        indices = [b["index"] for b in blocks]
        assert indices == [0, 1, 2, 3, 4]
        assert blocks[1]["type"] == "code"
        assert blocks[1]["metadata"].get("language") == "python"
        assert blocks[3]["type"] == "code"
        assert blocks[3]["metadata"].get("language") == "tsx"

    def test_unclosed_code_block_flushes(self) -> None:
        parser = StreamingArtifactParser()
        chunks = _all_chunks(parser, "```python\nprint(1)")
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "code"
        assert blocks[0]["metadata"].get("language") == "python"
        assert "print(1)" in blocks[0]["code"]

    def test_empty_feed_and_empty_flush(self) -> None:
        parser = StreamingArtifactParser()
        assert parser.feed("") == []
        assert parser.flush() == []

    def test_language_uses_first_token_only(self) -> None:
        parser = StreamingArtifactParser()
        chunks = _all_chunks(parser, "```python linenums\nprint(1)\n```")
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "code"
        assert blocks[0]["metadata"].get("language") == "python"

    def test_unclosed_language_uses_first_token_only(self) -> None:
        parser = StreamingArtifactParser()
        chunks = _all_chunks(parser, "```tsx preview")
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "code"
        assert blocks[0]["metadata"].get("language") == "tsx"

    def test_diff_fence_emits_diff_block(self) -> None:
        parser = StreamingArtifactParser()
        text = (
            "```diff\n"
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "```"
        )
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "diff"
        assert blocks[0]["metadata"].get("filename") == "changes.diff"
        assert "-old" in blocks[0]["text"]
        assert "+new" in blocks[0]["text"]

    def test_patch_fence_emits_diff_block(self) -> None:
        parser = StreamingArtifactParser()
        text = (
            "```patch\n"
            "--- a/foo.txt\n"
            "+++ b/foo.txt\n"
            "@@ -1 +1 @@\n"
            "-line\n"
            "+line\n"
            "```"
        )
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "diff"
        assert blocks[0]["metadata"].get("filename") == "changes.diff"

    def test_regular_code_fence_still_emits_code_block(self) -> None:
        parser = StreamingArtifactParser()
        text = "```python\nprint(1)\n```"
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "code"
        assert blocks[0]["metadata"].get("language") == "python"
        assert "print(1)" in blocks[0]["code"]

    def test_workflow_fence_emits_workflow_block(self) -> None:
        parser = StreamingArtifactParser()
        text = (
            "```workflow-yaml\n"
            "version: '1'\n"
            "name: Demo Flow\n"
            "nodes:\n"
            "  - id: start\n"
            "    type: trigger\n"
            "edges: []\n"
            "```"
        )
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "workflow"
        assert blocks[0]["metadata"].get("format") == "yaml"
        assert "Demo Flow" in blocks[0]["text"]

    def test_workflow_json_fence_emits_workflow_block(self) -> None:
        parser = StreamingArtifactParser()
        text = '```workflow-json\n{"version":"1","name":"Flow","nodes":[],"edges":[]}\n```'
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "workflow"
        assert blocks[0]["metadata"].get("format") == "json"
        assert '"name":"Flow"' in blocks[0]["text"]

    def test_standalone_url_emits_web_preview_block(self) -> None:
        parser = StreamingArtifactParser()
        text = "https://github.com/brqs/agenthub/pull/17"
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "web_preview"
        assert blocks[0]["metadata"].get("url") == "https://github.com/brqs/agenthub/pull/17"

    def test_inline_url_remains_text(self) -> None:
        parser = StreamingArtifactParser()
        text = "请看 https://example.com"
        chunks = _all_chunks(parser, text)
        blocks = _extract_blocks(chunks)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert "https://example.com" in blocks[0]["text"]

    def test_url_split_across_chunks_is_stable(self) -> None:
        parser = StreamingArtifactParser()
        chunks = []
        chunks.extend(parser.feed("https://"))
        chunks.extend(parser.feed("example.com\nworld"))
        chunks.extend(parser.flush())

        blocks = _extract_blocks(chunks)
        web_preview_blocks = [b for b in blocks if b["type"] == "web_preview"]
        assert len(web_preview_blocks) == 1
        assert web_preview_blocks[0]["metadata"].get("url") == "https://example.com"
        text_blocks = [b for b in blocks if b["type"] == "text"]
        assert any("world" in b["text"] for b in text_blocks)
        # Parser should not crash or lose content.
        assert not any(c.event_type == "error" for c in chunks)

    def test_incomplete_url_prefix_waits_for_host(self) -> None:
        parser = StreamingArtifactParser()
        chunks = []
        chunks.extend(parser.feed("https://"))
        # Buffer holds the incomplete URL – no block started yet.
        assert not any(c.event_type == "block_start" for c in chunks)

        chunks.extend(parser.flush())
        blocks = _extract_blocks(chunks)
        # https:// alone is not a valid URL – falls back to text.
        assert not any(b["type"] == "web_preview" for b in blocks)
        assert any("https://" in b["text"] for b in blocks)

    def test_url_prefix_completes_across_chunks(self) -> None:
        parser = StreamingArtifactParser()
        chunks = []
        chunks.extend(parser.feed("https://"))
        chunks.extend(parser.feed("example.com"))
        chunks.extend(parser.flush())

        blocks = _extract_blocks(chunks)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "web_preview"
        assert blocks[0]["metadata"].get("url") == "https://example.com"

    def test_diff_fence_split_across_chunks_is_stable(self) -> None:
        parser = StreamingArtifactParser()
        chunks = []
        chunks.extend(parser.feed("``"))
        chunks.extend(parser.feed("`diff\n--- a/app.py\n"))
        chunks.extend(parser.feed("+++ b/app.py\n``"))
        chunks.extend(parser.feed("`\n"))
        chunks.extend(parser.flush())

        blocks = _extract_blocks(chunks)
        diff_blocks = [b for b in blocks if b["type"] == "diff"]
        assert len(diff_blocks) == 1
        assert "--- a/app.py" in diff_blocks[0]["text"]
        assert "+++ b/app.py" in diff_blocks[0]["text"]
        # No triple-backtick should leak into deltas.
        for c in chunks:
            if c.event_type == "delta":
                assert "```" not in (c.text_delta or "")
                assert "```" not in (c.code_delta or "")
