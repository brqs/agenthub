"""
StreamingArtifactParser — splits LLM text stream into text/code ContentBlocks.

Uses a small state machine with three states:
  TEXT      → emitting plain text deltas
  CODE_LANG → just crossed an opening ```; parsing language tag
  CODE_BODY → emitting code deltas until closing ```

A tail buffer of up to 3 backticks is kept to avoid mid-fence splits.
"""

from __future__ import annotations

from app.agents.types import StreamChunk


class StreamingArtifactParser:
    """Stateful parser that converts streaming text → StreamChunk events."""

    def __init__(self) -> None:
        self.state: str = "TEXT"  # TEXT | CODE_LANG | CODE_BODY
        self._buffer: str = ""
        self.block_index: int = -1
        self._block_open: bool = False

    @staticmethod
    def _count_trailing_backticks(s: str) -> int:
        count = 0
        for ch in reversed(s):
            if ch == "`":
                count += 1
            else:
                break
        return count

    @staticmethod
    def _parse_language(raw: str) -> str:
        """Extract the first whitespace-delimited token as language."""
        parts = raw.strip().split()
        return parts[0] if parts else "text"

    def feed(self, text: str) -> list[StreamChunk]:
        """Feed a piece of streaming text, return new chunks to yield."""
        self._buffer += text
        return self._process()

    def _process(self) -> list[StreamChunk]:
        chunks: list[StreamChunk] = []

        while self._buffer:
            if self.state == "TEXT":
                idx = self._buffer.find("```")
                if idx == -1:
                    # No fence yet — emit everything except trailing backticks.
                    backticks = self._count_trailing_backticks(self._buffer)
                    if backticks == len(self._buffer):
                        # Entire buffer is backticks; keep them all.
                        break
                    to_output = self._buffer[:-backticks] if backticks else self._buffer
                    self._buffer = self._buffer[-backticks:] if backticks else ""
                    if to_output:
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
                            StreamChunk(
                                event_type="delta",
                                block_index=self.block_index,
                                text_delta=to_output,
                            )
                        )
                    break

                # Found an opening fence.
                before = self._buffer[:idx]
                if before:
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
                        StreamChunk(
                            event_type="delta",
                            block_index=self.block_index,
                            text_delta=before,
                        )
                    )
                if self._block_open:
                    chunks.append(
                        StreamChunk(
                            event_type="block_end",
                            block_index=self.block_index,
                        )
                    )
                    self._block_open = False

                after = self._buffer[idx + 3 :]
                self._buffer = after
                self.block_index += 1
                self.state = "CODE_LANG"
                continue

            if self.state == "CODE_LANG":
                if self._buffer.startswith("\n"):
                    lang = "text"
                    self._buffer = self._buffer[1:]
                else:
                    newline = self._buffer.find("\n")
                    if newline == -1:
                        # Incomplete language line — wait for more input.
                        break
                    lang = self._parse_language(self._buffer[:newline])
                    self._buffer = self._buffer[newline + 1 :]

                self._block_open = True
                chunks.append(
                    StreamChunk(
                        event_type="block_start",
                        block_index=self.block_index,
                        block_type="code",
                        metadata={"language": lang},
                    )
                )
                self.state = "CODE_BODY"
                continue

            if self.state == "CODE_BODY":
                idx = self._buffer.find("```")
                if idx == -1:
                    backticks = self._count_trailing_backticks(self._buffer)
                    if backticks == len(self._buffer):
                        break
                    to_output = self._buffer[:-backticks] if backticks else self._buffer
                    self._buffer = self._buffer[-backticks:] if backticks else ""
                    if to_output:
                        chunks.append(
                            StreamChunk(
                                event_type="delta",
                                block_index=self.block_index,
                                code_delta=to_output,
                            )
                        )
                    break

                # Found a closing fence.
                before = self._buffer[:idx]
                if before:
                    chunks.append(
                        StreamChunk(
                            event_type="delta",
                            block_index=self.block_index,
                            code_delta=before,
                        )
                    )
                chunks.append(
                    StreamChunk(
                        event_type="block_end",
                        block_index=self.block_index,
                    )
                )
                self._block_open = False

                after = self._buffer[idx + 3 :]
                if after.startswith("\n"):
                    after = after[1:]
                self._buffer = after
                self.state = "TEXT"
                continue

        return chunks

    def flush(self) -> list[StreamChunk]:
        """Flush any buffered content at end of stream."""
        chunks: list[StreamChunk] = []

        if self.state == "CODE_LANG":
            lang = self._parse_language(self._buffer)
            self._block_open = True
            chunks.append(
                StreamChunk(
                    event_type="block_start",
                    block_index=self.block_index,
                    block_type="code",
                    metadata={"language": lang},
                )
            )
            self.state = "CODE_BODY"
            self._buffer = ""

        if self.state == "CODE_BODY":
            if self._buffer:
                chunks.append(
                    StreamChunk(
                        event_type="delta",
                        block_index=self.block_index,
                        code_delta=self._buffer,
                    )
                )
                self._buffer = ""
            if self._block_open:
                chunks.append(
                    StreamChunk(
                        event_type="block_end",
                        block_index=self.block_index,
                    )
                )
                self._block_open = False
            self.state = "TEXT"

        if self.state == "TEXT":
            if self._buffer:
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
                    StreamChunk(
                        event_type="delta",
                        block_index=self.block_index,
                        text_delta=self._buffer,
                    )
                )
                self._buffer = ""
            if self._block_open:
                chunks.append(
                    StreamChunk(
                        event_type="block_end",
                        block_index=self.block_index,
                    )
                )
                self._block_open = False

        return chunks
