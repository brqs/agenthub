"""
StreamingArtifactParser — splits LLM text stream into text/code ContentBlocks.

TODO(B2):
  - Implement the state machine described in docs/tech-architecture.md § 6.4.
  - Detect ``` code fences in streaming text and switch block types.
  - Buffer the tail (≤3 chars) to avoid mid-fence splits.
"""

from __future__ import annotations

from app.agents.types import StreamChunk


class StreamingArtifactParser:
    """Stateful parser that converts streaming text → StreamChunk events."""

    def __init__(self) -> None:
        self.state: str = "TEXT"  # "TEXT" | "CODE"
        self.buffer: str = ""
        self.block_index: int = -1
        self._block_open: bool = False

    def feed(self, text: str) -> list[StreamChunk]:
        """Feed a piece of streaming text, return new chunks to yield."""
        # TODO(B2): implement state machine
        chunks: list[StreamChunk] = []
        if not self._block_open:
            self.block_index += 1
            self._block_open = True
            chunks.append(
                StreamChunk(
                    event_type="block_start",
                    block_index=self.block_index,
                    block_type="text",
                )
            )
        chunks.append(
            StreamChunk(event_type="delta", block_index=self.block_index, text_delta=text)
        )
        return chunks

    def flush(self) -> list[StreamChunk]:
        """Flush any buffered content at end of stream."""
        chunks: list[StreamChunk] = []
        if self._block_open:
            chunks.append(StreamChunk(event_type="block_end", block_index=self.block_index))
            self._block_open = False
        return chunks
