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
