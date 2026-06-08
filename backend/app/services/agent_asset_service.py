"""Custom Agent knowledge and skill asset helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.agent import Agent
from app.models.upload import Upload
from app.schemas.agent import AgentKnowledgeOut, AgentKnowledgeUsage, AgentSkillOut
from app.services.upload_service import upload_service

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".txt"}
SKILL_EXTENSIONS = {".md", ".markdown"}


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
        value = _short_text(raw_value.strip().strip("\"'"))
        if key and value:
            metadata[key] = value
    return metadata


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
