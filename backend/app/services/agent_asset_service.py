"""Custom Agent knowledge and skill asset helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.models.agent import Agent
from app.models.upload import Upload
from app.schemas.agent import AgentKnowledgeOut, AgentKnowledgeUsage, AgentSkillOut
from app.services.upload_service import upload_service

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".txt"}
SKILL_EXTENSIONS = {".md", ".markdown"}
DEFAULT_ASSET_CONTEXT_MAX_CHARS = 12000
ASSET_ITEM_MAX_CHARS = 3000


class AgentAssetService:
    async def create_knowledge(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        file: UploadFile,
        label: str | None,
        usage: AgentKnowledgeUsage,
    ) -> tuple[Agent, AgentKnowledgeOut]:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        self._assert_extension(file.filename, MARKDOWN_EXTENSIONS, "UNSUPPORTED_KNOWLEDGE_FILE")
        upload = await upload_service.create_upload(
            db,
            user_id=user_id,
            conversation_id=None,
            purpose="agent_knowledge",
            file=file,
        )
        item = self._knowledge_out(upload, label=label, usage=usage)
        config = _config_copy(agent)
        entries = [
            entry
            for entry in _list_config_items(config, "knowledge")
            if str(entry.get("upload_id")) != str(item.upload_id)
        ]
        entries.append(item.model_dump(mode="json"))
        config["knowledge"] = entries
        agent.config = config
        flag_modified(agent, "config")
        await db.flush()
        return agent, item

    async def delete_knowledge(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        upload_id: UUID,
    ) -> Agent:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        config = _config_copy(agent)
        before = _list_config_items(config, "knowledge")
        config["knowledge"] = [
            entry for entry in before if str(entry.get("upload_id")) != str(upload_id)
        ]
        agent.config = config
        flag_modified(agent, "config")
        await db.flush()
        return agent

    async def update_knowledge(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        upload_id: UUID,
        label: str | None,
        usage: AgentKnowledgeUsage | None,
    ) -> tuple[Agent, AgentKnowledgeOut]:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        config = _config_copy(agent)
        entries = _list_config_items(config, "knowledge")
        index = _find_config_item_index(entries, "upload_id", str(upload_id))
        if index is None:
            raise_asset_not_found("AGENT_KNOWLEDGE_NOT_FOUND")
        if label is not None:
            entries[index]["label"] = _short_text(label) or entries[index].get("label")
        if usage is not None:
            entries[index]["usage"] = usage
        config["knowledge"] = entries
        agent.config = config
        flag_modified(agent, "config")
        await db.flush()
        return agent, AgentKnowledgeOut.model_validate(entries[index])

    async def create_skill(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        file: UploadFile,
        name: str | None,
        description: str | None,
    ) -> tuple[Agent, AgentSkillOut]:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        self._assert_extension(file.filename, SKILL_EXTENSIONS, "UNSUPPORTED_SKILL_FILE")
        skill_preview_text = await _read_upload_file_text_preview(file)
        _validate_skill_fields(skill_preview_text, name=name, description=description)
        await file.seek(0)
        upload = await upload_service.create_upload(
            db,
            user_id=user_id,
            conversation_id=None,
            purpose="skill_package",
            file=file,
        )
        item = self._skill_out(upload, name=name, description=description)
        config = _config_copy(agent)
        entries = [
            entry
            for entry in _list_config_items(config, "skills")
            if str(entry.get("skill_id")) != item.skill_id
        ]
        entries.append(item.model_dump(mode="json"))
        config["skills"] = entries
        agent.config = config
        flag_modified(agent, "config")
        await db.flush()
        return agent, item

    async def delete_skill(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        skill_id: str,
    ) -> Agent:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        config = _config_copy(agent)
        before = _list_config_items(config, "skills")
        config["skills"] = [entry for entry in before if str(entry.get("skill_id")) != skill_id]
        agent.config = config
        flag_modified(agent, "config")
        await db.flush()
        return agent

    async def update_skill(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        skill_id: str,
        name: str | None,
        description: str | None,
    ) -> tuple[Agent, AgentSkillOut]:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        config = _config_copy(agent)
        entries = _list_config_items(config, "skills")
        index = _find_config_item_index(entries, "skill_id", skill_id)
        if index is None:
            raise_asset_not_found("AGENT_SKILL_NOT_FOUND")
        if name is not None:
            entries[index]["name"] = _short_text(name) or entries[index].get("name")
        if description is not None:
            entries[index]["description"] = _short_text(description, max_len=240) or entries[
                index
            ].get("description")
        config["skills"] = entries
        agent.config = config
        flag_modified(agent, "config")
        await db.flush()
        return agent, AgentSkillOut.model_validate(entries[index])

    async def _owned_custom_agent(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
    ) -> Agent:
        agent = await db.get(Agent, agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "AGENT_NOT_FOUND", "message": "Not found"}},
            )
        if agent.is_builtin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "CANNOT_MODIFY_BUILTIN",
                        "message": "Built-in agents are read-only",
                    }
                },
            )
        if agent.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}},
            )
        return agent

    def _knowledge_out(
        self,
        upload: Upload,
        *,
        label: str | None,
        usage: AgentKnowledgeUsage,
    ) -> AgentKnowledgeOut:
        return AgentKnowledgeOut(
            upload_id=upload.id,
            filename=upload.filename,
            label=_short_text(label) or upload.filename,
            usage=usage,
            content_type=upload.detected_content_type or upload.content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            created_at=upload.created_at,
        )

    def _skill_out(
        self,
        upload: Upload,
        *,
        name: str | None,
        description: str | None,
    ) -> AgentSkillOut:
        preview = upload.preview if isinstance(upload.preview, dict) else {}
        text = str(preview.get("text_preview") or "")
        metadata = _parse_skill_metadata(text)
        normalized_name = _short_text(name) or metadata.get("name") or _first_heading(text)
        normalized_description = (
            _short_text(description) or metadata.get("description") or _first_body_line(text)
        )
        return AgentSkillOut(
            skill_id=f"skill_{uuid4().hex}",
            upload_id=upload.id,
            name=normalized_name or Path(upload.filename).stem or "Uploaded Skill",
            description=normalized_description or "用户上传的 Agent skill。",
            filename=upload.filename,
            content_type=upload.detected_content_type or upload.content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            created_at=upload.created_at,
            metadata=metadata,
        )

    def _assert_extension(
        self,
        filename: str | None,
        allowed: set[str],
        code: str,
    ) -> None:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in allowed:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={
                    "error": {
                        "code": code,
                        "message": "Only Markdown/text files are supported for this Agent asset",
                    }
                },
            )


def _config_copy(agent: Agent) -> dict[str, Any]:
    return dict(agent.config or {})


def _list_config_items(config: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = config.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _find_config_item_index(
    entries: list[dict[str, Any]],
    key: str,
    value: str,
) -> int | None:
    for index, entry in enumerate(entries):
        if str(entry.get(key)) == value:
            return index
    return None


def raise_asset_not_found(code: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": code, "message": "Agent asset binding not found"}},
    )


def _short_text(value: str | None, *, max_len: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized[:max_len] if normalized else None


def _parse_skill_metadata(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    metadata: dict[str, Any] = {}
    for raw_line in text[3:end].splitlines():
        if ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        value = _parse_metadata_value(raw_value)
        if key and value:
            metadata[key] = value
    return metadata


async def _read_upload_file_text_preview(file: UploadFile) -> str:
    raw = await file.read(settings.upload_preview_max_bytes + 1)
    return raw.decode("utf-8", errors="replace")


def _validate_skill_fields(
    text: str,
    *,
    name: str | None,
    description: str | None,
) -> None:
    metadata = _parse_skill_metadata(text)
    normalized_name = _short_text(name) or metadata.get("name") or _first_heading(text)
    normalized_description = (
        _short_text(description) or metadata.get("description") or _first_body_line(text)
    )
    missing: list[str] = []
    if not normalized_name:
        missing.append("name")
    if not normalized_description:
        missing.append("description")
    if not missing:
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "error": {
                "code": "INVALID_SKILL_METADATA",
                "message": "Skill Markdown must provide name and description",
                "details": {"missing_fields": missing},
            }
        },
    )


def _parse_metadata_value(raw_value: str) -> Any:
    stripped = raw_value.strip().strip("\"'")
    if not stripped:
        return None
    if stripped.startswith("[") and stripped.endswith("]"):
        items = [_short_text(item.strip().strip("\"'")) for item in stripped[1:-1].split(",")]
        return [item for item in items if item]
    return _short_text(stripped)


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return _short_text(stripped.lstrip("#").strip())
    return None


def _first_body_line(text: str) -> str | None:
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            body = text[end + 4 :]
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        return _short_text(stripped, max_len=240)
    return None


agent_asset_service = AgentAssetService()


async def build_agent_asset_context(
    db: AsyncSession,
    agent: Agent,
    *,
    max_chars: int = DEFAULT_ASSET_CONTEXT_MAX_CHARS,
) -> str:
    """Build bounded prompt context from user-approved custom Agent assets."""
    if not agent.user_id:
        return ""
    config = _config_copy(agent)
    sections: list[str] = []
    knowledge = await _knowledge_context(db, agent, _list_config_items(config, "knowledge"))
    if knowledge:
        sections.append("## Agent Knowledge\n" + "\n\n".join(knowledge))
    skills = await _skill_context(db, agent, _list_config_items(config, "skills"))
    if skills:
        sections.append("## Agent Skills\n" + "\n\n".join(skills))
    if not sections:
        return ""
    context = (
        "The user explicitly attached the following custom Agent assets. "
        "Use them when relevant and do not assume unavailable files contain more than shown.\n\n"
        + "\n\n".join(sections)
    )
    return context[:max_chars]


def append_agent_asset_context(system_prompt: str | None, asset_context: str) -> str | None:
    if not asset_context:
        return system_prompt
    base = (system_prompt or "").strip()
    section = f"<agent_uploaded_assets>\n{asset_context}\n</agent_uploaded_assets>"
    return f"{base}\n\n{section}" if base else section


async def _knowledge_context(
    db: AsyncSession,
    agent: Agent,
    entries: list[dict[str, Any]],
) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        upload = await _safe_asset_upload(db, agent, entry.get("upload_id"))
        if upload is None:
            continue
        label = _short_text(str(entry.get("label") or upload.filename)) or upload.filename
        usage = _short_text(str(entry.get("usage") or "reference")) or "reference"
        content = _read_upload_text(upload)
        if not content:
            continue
        lines.append(f"### {label}\n- file: {upload.filename}\n- usage: {usage}\n\n{content}")
    return lines


async def _skill_context(
    db: AsyncSession,
    agent: Agent,
    entries: list[dict[str, Any]],
) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        upload = await _safe_asset_upload(db, agent, entry.get("upload_id"))
        if upload is None:
            continue
        name = _short_text(str(entry.get("name") or Path(upload.filename).stem)) or upload.filename
        description = _short_text(str(entry.get("description") or "Uploaded Agent skill."))
        content = _read_upload_text(upload)
        if not content:
            continue
        lines.append(
            f"### {name}\n"
            f"- file: {upload.filename}\n"
            f"- description: {description or 'Uploaded Agent skill.'}\n\n"
            f"{content}"
        )
    return lines


async def _safe_asset_upload(
    db: AsyncSession,
    agent: Agent,
    upload_id: object,
) -> Upload | None:
    if not isinstance(upload_id, str):
        return None
    try:
        parsed = UUID(upload_id)
    except ValueError:
        return None
    upload = await db.get(Upload, parsed)
    if upload is None:
        return None
    if upload.owner_user_id != agent.user_id:
        return None
    if upload.status != "ready" or upload.safety_status != "passed":
        return None
    suffix = Path(upload.filename).suffix.lower()
    content_type = upload.detected_content_type or upload.content_type
    if suffix not in MARKDOWN_EXTENSIONS and not content_type.startswith("text/"):
        return None
    return upload


def _read_upload_text(upload: Upload) -> str:
    path = Path(upload.storage_key)
    if not path.is_file():
        return ""
    max_bytes = max(settings.upload_preview_max_bytes, ASSET_ITEM_MAX_CHARS * 4)
    raw = path.read_bytes()[: max_bytes + 1]
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    if len(text) > ASSET_ITEM_MAX_CHARS:
        return text[:ASSET_ITEM_MAX_CHARS] + "\n...[truncated]"
    if len(raw) > max_bytes:
        return text + "\n...[truncated]"
    return text
