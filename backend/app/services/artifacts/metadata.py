"""Workspace artifact classification and preview metadata helpers."""

from __future__ import annotations

import mimetypes
import struct
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree

ArtifactKind = Literal["document", "ppt", "image", "archive", "code", "workflow", "other"]

TEXT_PREVIEW_MAX_CHARS = 4096
ARCHIVE_MAX_ENTRIES = 200
ARCHIVE_MAX_TOTAL_BYTES = 50 * 1024 * 1024
ARCHIVE_TOP_ENTRY_COUNT = 8

DOCUMENT_SUFFIXES = {".md", ".txt", ".csv", ".pdf", ".docx"}
TEXT_PREVIEW_SUFFIXES = {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}
PPT_SUFFIXES = {".ppt", ".pptx"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".toml", ".xml"}
WORKFLOW_SUFFIXES = {".json", ".yaml", ".yml"}
ARCHIVE_SUFFIXES = {".zip", ".tar", ".tgz", ".tar.gz"}


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    path: str
    filename: str
    size: int
    mime_type: str
    artifact_kind: ArtifactKind
    preview_text: str | None = None
    preview_truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def build_artifact_metadata(path: Path, rel_path: str) -> ArtifactMetadata:
    """Return user-facing metadata for a workspace artifact file."""

    suffix = _artifact_suffix(rel_path)
    mime_type = _guess_mime_type(rel_path)
    artifact_kind = classify_artifact(rel_path, mime_type)
    size = path.stat().st_size
    preview_text: str | None = None
    preview_truncated = False
    metadata: dict[str, Any] = {}

    if suffix in TEXT_PREVIEW_SUFFIXES:
        preview_text, preview_truncated = _read_preview_text(path)
    if artifact_kind == "ppt":
        ppt_meta = _ppt_metadata(path, suffix)
        metadata.update(ppt_meta)
        if preview_text is None and "preview_text" in ppt_meta:
            preview_text = str(ppt_meta.pop("preview_text"))
            preview_truncated = False
    elif artifact_kind == "image":
        metadata.update(_image_metadata(path, suffix))
    elif artifact_kind == "archive":
        metadata.update(_archive_metadata(path, suffix))

    return ArtifactMetadata(
        path=rel_path,
        filename=Path(rel_path).name,
        size=size,
        mime_type=mime_type,
        artifact_kind=artifact_kind,
        preview_text=preview_text,
        preview_truncated=preview_truncated,
        metadata=metadata,
    )


def classify_artifact(path: str, mime_type: str | None = None) -> ArtifactKind:
    lowered = path.lower()
    suffix = _artifact_suffix(lowered)
    if "workflow" in lowered and suffix in WORKFLOW_SUFFIXES:
        return "workflow"
    if suffix in ARCHIVE_SUFFIXES:
        return "archive"
    if suffix in IMAGE_SUFFIXES or (mime_type or "").startswith("image/"):
        return "image"
    if suffix in PPT_SUFFIXES or "ppt_outline" in lowered or "slides" in lowered:
        return "ppt"
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    if suffix in CODE_SUFFIXES:
        return "code"
    return "other"


def validate_image_artifact(path: Path) -> tuple[bool, dict[str, Any], str | None]:
    suffix = _artifact_suffix(path.name)
    if path.stat().st_size <= 0:
        return False, {}, "image_empty"
    metadata = _image_metadata(path, suffix)
    if metadata.get("error"):
        return False, metadata, str(metadata["error"])
    return True, metadata, None


def validate_archive_artifact(path: Path) -> tuple[bool, dict[str, Any], str | None]:
    suffix = _artifact_suffix(path.name)
    metadata = _archive_metadata(path, suffix)
    if metadata.get("error"):
        return False, metadata, str(metadata["error"])
    if int(metadata.get("file_count") or 0) <= 0:
        return False, metadata, "archive_empty"
    return True, metadata, None


def read_pptx_slide_text(path: Path) -> list[str]:
    """Extract slide text from a pptx OpenXML archive."""

    slides: list[tuple[str, str]] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            try:
                root = ElementTree.fromstring(archive.read(name))  # noqa: S314
            except ElementTree.ParseError:
                continue
            texts = [
                node.text.strip()
                for node in root.iter()
                if node.tag.endswith("}t") and node.text and node.text.strip()
            ]
            slides.append((name, "\n".join(texts)))
    return [text for _, text in sorted(slides)]


def _artifact_suffix(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".tar.gz"):
        return ".tar.gz"
    return Path(lowered).suffix


def _guess_mime_type(path: str) -> str:
    if path.lower().endswith(".md"):
        return "text/markdown"
    if path.lower().endswith(".pptx"):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if path.lower().endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    mime_type, _ = mimetypes.guess_type(path)
    return mime_type or "application/octet-stream"


def _read_preview_text(path: Path) -> tuple[str | None, bool]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, False
    if len(raw) <= TEXT_PREVIEW_MAX_CHARS:
        return raw, False
    return raw[:TEXT_PREVIEW_MAX_CHARS], True


def _ppt_metadata(path: Path, suffix: str) -> dict[str, Any]:
    if suffix == ".pptx":
        try:
            slides = read_pptx_slide_text(path)
        except (zipfile.BadZipFile, KeyError):
            return {"error": "pptx_parse_error"}
        return {
            "slide_count": len(slides),
            "preview_text": "\n\n---\n\n".join(slides[:5]),
        }
    if path.suffix.lower() in {".md", ".txt"} or path.name.lower().endswith("ppt_outline.json"):
        preview, _ = _read_preview_text(path)
        if not preview:
            return {}
        slide_count = max(
            1,
            sum(1 for line in preview.splitlines() if line.lstrip().startswith("#"))
            or preview.count("\n---"),
        )
        return {"slide_count": slide_count}
    return {}


def _image_metadata(path: Path, suffix: str) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError:
        return {"error": "image_read_error"}
    if not data:
        return {"error": "image_empty"}
    if suffix == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
            return {"error": "image_header_invalid"}
        width, height = struct.unpack(">II", data[16:24])
        return {"width": width, "height": height}
    if suffix in {".jpg", ".jpeg"}:
        size = _jpeg_size(data)
        return size if size else {"error": "image_header_invalid"}
    if suffix == ".gif":
        if not data.startswith((b"GIF87a", b"GIF89a")) or len(data) < 10:
            return {"error": "image_header_invalid"}
        width, height = struct.unpack("<HH", data[6:10])
        return {"width": width, "height": height}
    if suffix == ".webp":
        if not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
            return {"error": "image_header_invalid"}
        return {"format": "webp"}
    if suffix == ".svg":
        try:
            root = ElementTree.fromstring(data)  # noqa: S314
        except ElementTree.ParseError:
            return {"error": "svg_parse_error"}
        if not root.tag.lower().endswith("svg"):
            return {"error": "svg_root_invalid"}
        return {
            "width": root.attrib.get("width"),
            "height": root.attrib.get("height"),
            "viewBox": root.attrib.get("viewBox"),
        }
    return {"error": "image_type_unsupported"}


def _jpeg_size(data: bytes) -> dict[str, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if index + 7 > len(data):
                return None
            height, width = struct.unpack(">HH", data[index + 3 : index + 7])
            return {"width": width, "height": height}
        index += segment_length
    return None


def _archive_metadata(path: Path, suffix: str) -> dict[str, Any]:
    try:
        if suffix == ".zip":
            return _zip_metadata(path)
        if suffix in {".tar", ".tgz", ".tar.gz"}:
            return _tar_metadata(path)
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        return {"error": "archive_parse_error"}
    return {"error": "archive_type_unsupported"}


def _zip_metadata(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        return _archive_entries_metadata(
            [(item.filename, item.file_size) for item in infos]
        )


def _tar_metadata(path: Path) -> dict[str, Any]:
    if _artifact_suffix(path.name) in {".tgz", ".tar.gz"}:
        with tarfile.open(path, "r:gz") as archive:
            members = [item for item in archive.getmembers() if item.isfile()]
    else:
        with tarfile.open(path, "r:") as archive:
            members = [item for item in archive.getmembers() if item.isfile()]
    return _archive_entries_metadata([(item.name, int(item.size)) for item in members])


def _archive_entries_metadata(entries: list[tuple[str, int]]) -> dict[str, Any]:
    if len(entries) > ARCHIVE_MAX_ENTRIES:
        return {"error": "archive_too_many_entries", "file_count": len(entries)}
    total_size = sum(size for _, size in entries)
    if total_size > ARCHIVE_MAX_TOTAL_BYTES:
        return {"error": "archive_too_large", "file_count": len(entries)}
    for name, _ in entries:
        normalized = Path(name.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            return {"error": "archive_path_traversal", "file_count": len(entries)}
    return {
        "file_count": len(entries),
        "total_size": total_size,
        "top_entries": [name for name, _ in entries[:ARCHIVE_TOP_ENTRY_COUNT]],
    }
