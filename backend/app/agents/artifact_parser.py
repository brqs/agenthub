"""
StreamingArtifactParser — splits LLM text stream into text/code/diff/web_preview ContentBlocks.

Uses a small state machine with three states:
  TEXT      → emitting plain text deltas (with standalone URL detection)
  CODE_LANG → just crossed an opening ```; parsing language tag
  CODE_BODY → emitting code/diff deltas until closing ```

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
        self._current_block_type: str = "text"

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

    @staticmethod
    def _is_standalone_url(line: str) -> bool:
        """Return True if *line* is a complete standalone http(s) URL."""
        stripped = line.strip()
        if not stripped:
            return False
        if not (stripped.startswith("http://") or stripped.startswith("https://")):
            return False
        if " " in stripped:
            return False
        # Must contain a dot after the scheme to be a valid host
        remainder = stripped[stripped.find("://") + 3 :]
        return "." in remainder

    def _emit_text_buffer(self, text: str, chunks: list[StreamChunk]) -> None:
        """Emit *text* as text deltas, splitting out standalone URLs."""
        last_newline = text.rfind("\n")
        if last_newline == -1:
            # No complete line – could be a standalone URL or plain text.
            if self._is_standalone_url(text):
                if self._block_open and self._current_block_type == "text":
                    chunks.append(
                        StreamChunk(
                            event_type="block_end",
                            block_index=self.block_index,
                        )
                    )
                    self._block_open = False
                self.block_index += 1
                self._block_open = True
                self._current_block_type = "web_preview"
                chunks.append(
                    StreamChunk(
                        event_type="block_start",
                        block_index=self.block_index,
                        block_type="web_preview",
                        metadata={"url": text.strip()},
                    )
                )
                chunks.append(
                    StreamChunk(
                        event_type="block_end",
                        block_index=self.block_index,
                    )
                )
                self._block_open = False
                return
            if text:
                if not self._block_open:
                    self.block_index += 1
                    self._block_open = True
                    self._current_block_type = "text"
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
                        text_delta=text,
                    )
                )
            return

        to_process = text[: last_newline + 1]
        trailing = text[last_newline + 1 :]

        i = 0
        while i < len(to_process):
            nl = to_process.find("\n", i)
            if nl == -1:
                break
            line_with_nl = to_process[i : nl + 1]
            i = nl + 1
            line_content = line_with_nl.rstrip("\n")

            if self._is_standalone_url(line_content):
                if self._block_open and self._current_block_type == "text":
                    chunks.append(
                        StreamChunk(
                            event_type="block_end",
                            block_index=self.block_index,
                        )
                    )
                    self._block_open = False
                self.block_index += 1
                self._block_open = True
                self._current_block_type = "web_preview"
                chunks.append(
                    StreamChunk(
                        event_type="block_start",
                        block_index=self.block_index,
                        block_type="web_preview",
                        metadata={"url": line_content.strip()},
                    )
                )
                chunks.append(
                    StreamChunk(
                        event_type="block_end",
                        block_index=self.block_index,
                    )
                )
                self._block_open = False
            else:
                if not self._block_open:
                    self.block_index += 1
                    self._block_open = True
                    self._current_block_type = "text"
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
                        text_delta=line_with_nl,
                    )
                )

        if trailing:
            if not self._block_open:
                self.block_index += 1
                self._block_open = True
                self._current_block_type = "text"
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
                    text_delta=trailing,
                )
            )

    def feed(self, text: str) -> list[StreamChunk]:
        """Feed a piece of streaming text, return new chunks to yield."""
        self._buffer += text
        return self._process()

    def _process(self) -> list[StreamChunk]:
        chunks: list[StreamChunk] = []

        while self._buffer:
            if self.state == "TEXT":
                idx = self._buffer.find("```")
                if idx != -1:
                    before = self._buffer[:idx]
                    if before:
                        self._emit_text_buffer(before, chunks)
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

                # No fence yet – try to process complete lines for URL detection.
                last_newline = self._buffer.rfind("\n")
                if last_newline != -1:
                    to_process = self._buffer[: last_newline + 1]
                    self._buffer = self._buffer[last_newline + 1 :]
                    self._emit_text_buffer(to_process, chunks)
                    continue

                # No complete line – fall back to trailing-backtick logic.
                # Conservative: if buffer looks like an incomplete URL, wait.
                stripped = self._buffer.strip()
                if stripped.startswith(("http://", "https://")):
                    break

                backticks = self._count_trailing_backticks(self._buffer)
                if backticks == len(self._buffer):
                    break
                to_output = self._buffer[:-backticks] if backticks else self._buffer
                self._buffer = self._buffer[-backticks:] if backticks else ""
                if to_output:
                    self._emit_text_buffer(to_output, chunks)
                break

            if self.state == "CODE_LANG":
                if self._buffer.startswith("\n"):
                    lang = "text"
                    self._buffer = self._buffer[1:]
                else:
                    newline = self._buffer.find("\n")
                    if newline == -1:
                        break
                    lang = self._parse_language(self._buffer[:newline])
                    self._buffer = self._buffer[newline + 1 :]

                self._block_open = True
                if lang in {"diff", "patch", "udiff"}:
                    block_type = "diff"
                    metadata: dict[str, str] = {"filename": "changes.diff"}
                    self._current_block_type = "diff"
                else:
                    block_type = "code"
                    metadata = {"language": lang}
                    self._current_block_type = "code"
                chunks.append(
                    StreamChunk(
                        event_type="block_start",
                        block_index=self.block_index,
                        block_type=block_type,
                        metadata=metadata,
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
                        if self._current_block_type == "diff":
                            chunks.append(
                                StreamChunk(
                                    event_type="delta",
                                    block_index=self.block_index,
                                    text_delta=to_output,
                                )
                            )
                        else:
                            chunks.append(
                                StreamChunk(
                                    event_type="delta",
                                    block_index=self.block_index,
                                    code_delta=to_output,
                                )
                            )
                    break

                before = self._buffer[:idx]
                if before:
                    if self._current_block_type == "diff":
                        chunks.append(
                            StreamChunk(
                                event_type="delta",
                                block_index=self.block_index,
                                text_delta=before,
                            )
                        )
                    else:
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
                self._current_block_type = "text"
                continue

        return chunks

    def flush(self) -> list[StreamChunk]:
        """Flush any buffered content at end of stream."""
        chunks: list[StreamChunk] = []

        if self.state == "CODE_LANG":
            lang = self._parse_language(self._buffer)
            self._block_open = True
            if lang in {"diff", "patch", "udiff"}:
                block_type = "diff"
                metadata = {"filename": "changes.diff"}
                self._current_block_type = "diff"
            else:
                block_type = "code"
                metadata = {"language": lang}
                self._current_block_type = "code"
            chunks.append(
                StreamChunk(
                    event_type="block_start",
                    block_index=self.block_index,
                    block_type=block_type,
                    metadata=metadata,
                )
            )
            self.state = "CODE_BODY"
            self._buffer = ""

        if self.state == "CODE_BODY":
            if self._buffer:
                if self._current_block_type == "diff":
                    chunks.append(
                        StreamChunk(
                            event_type="delta",
                            block_index=self.block_index,
                            text_delta=self._buffer,
                        )
                    )
                else:
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
            self._current_block_type = "text"

        if self.state == "TEXT":
            if self._buffer:
                self._emit_text_buffer(self._buffer, chunks)
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
