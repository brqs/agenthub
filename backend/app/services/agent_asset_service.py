"""Custom Agent knowledge and skill asset helpers."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.models.agent import Agent
from app.models.agent_asset import AgentAssetBinding, AgentAssetUsageEvent, AgentAssetVersion
from app.models.upload import Upload
from app.schemas.agent import (
    AgentAssetBindingOut,
    AgentAssetHistoryOut,
    AgentAssetsOut,
    AgentAssetUsageEventOut,
    AgentAssetUsageListOut,
    AgentAssetVersionOut,
    AgentKnowledgeOut,
    AgentKnowledgeUsage,
    AgentSkillOut,
)
from app.services.upload_service import upload_service

logger = logging.getLogger(__name__)

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".txt"}
SKILL_EXTENSIONS = {".md", ".markdown"}
DEFAULT_ASSET_CONTEXT_MAX_CHARS = 12000
ASSET_ITEM_MAX_CHARS = 3000


class AgentAssetService:
    async def list_assets(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
    ) -> AgentAssetsOut:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        await self._materialize_legacy_bindings(db, agent, actor_user_id=user_id)
        return await self._assets_out(db, agent)

    async def list_history(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        limit: int,
    ) -> AgentAssetHistoryOut:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        await self._materialize_legacy_bindings(db, agent, actor_user_id=user_id)
        base = (
            select(AgentAssetVersion)
            .join(AgentAssetBinding, AgentAssetVersion.binding_id == AgentAssetBinding.id)
            .where(AgentAssetBinding.agent_id == agent.id)
        )
        total = (
            await db.execute(
                select(func.count()).select_from(
                    base.with_only_columns(AgentAssetVersion.id).subquery()
                )
            )
        ).scalar_one()
        rows = (
            await db.execute(
                base.order_by(AgentAssetVersion.created_at.desc(), AgentAssetVersion.version.desc())
                .limit(limit)
            )
        ).scalars()
        return AgentAssetHistoryOut(
            items=[self._version_out(item) for item in rows],
            total=total,
        )

    async def list_usage(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        limit: int,
    ) -> AgentAssetUsageListOut:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        base = select(AgentAssetUsageEvent).where(AgentAssetUsageEvent.agent_id == agent.id)
        total = (
            await db.execute(
                select(func.count()).select_from(
                    base.with_only_columns(AgentAssetUsageEvent.id).subquery()
                )
            )
        ).scalar_one()
        rows = (
            await db.execute(
                base.order_by(AgentAssetUsageEvent.created_at.desc()).limit(limit)
            )
        ).scalars()
        return AgentAssetUsageListOut(
            items=[self._usage_out(item) for item in rows],
            total=total,
        )

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
        binding = AgentAssetBinding(
            agent_id=agent.id,
            upload_id=upload.id,
            owner_user_id=user_id,
            kind="knowledge",
            status="active",
            label=_short_text(label) or upload.filename,
            usage=usage,
            metadata_={},
        )
        db.add(binding)
        await db.flush()
        await self._record_version(db, binding, action="created", actor_user_id=user_id)
        await self._sync_agent_config_from_bindings(db, agent)
        return agent, self._knowledge_out(binding, upload)

    async def delete_knowledge(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        agent_id: str,
        upload_id: UUID,
    ) -> Agent:
        agent = await self._owned_custom_agent(db, user_id=user_id, agent_id=agent_id)
        await self._materialize_legacy_bindings(db, agent, actor_user_id=user_id)
        binding = await self._find_binding(
            db,
            agent_id=agent.id,
            kind="knowledge",
            upload_id=upload_id,
        )
        if binding is None:
            raise_asset_not_found("AGENT_KNOWLEDGE_NOT_FOUND")
        binding.status = "unbound"
        binding.unbound_at = datetime.now(UTC)
        await db.flush()
        await self._record_version(db, binding, action="unbound", actor_user_id=user_id)
        await self._sync_agent_config_from_bindings(db, agent)
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
        await self._materialize_legacy_bindings(db, agent, actor_user_id=user_id)
        binding = await self._find_binding(
            db,
            agent_id=agent.id,
            kind="knowledge",
            upload_id=upload_id,
        )
        if binding is None:
            raise_asset_not_found("AGENT_KNOWLEDGE_NOT_FOUND")
        if label is not None:
            binding.label = _short_text(label) or binding.label
        if usage is not None:
            binding.usage = usage
        await db.flush()
        await self._record_version(db, binding, action="updated", actor_user_id=user_id)
        await self._sync_agent_config_from_bindings(db, agent)
        upload = await _required_upload(db, binding.upload_id)
        return agent, self._knowledge_out(binding, upload)

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
        item = self._skill_out_from_upload(upload, name=name, description=description)
        binding = AgentAssetBinding(
            agent_id=agent.id,
            upload_id=upload.id,
            owner_user_id=user_id,
            kind="skill",
            status="active",
            skill_id=item.skill_id,
            name=item.name,
            description=item.description,
            metadata_=item.metadata,
        )
        db.add(binding)
        await db.flush()
        await self._record_version(db, binding, action="created", actor_user_id=user_id)
        await self._sync_agent_config_from_bindings(db, agent)
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
        await self._materialize_legacy_bindings(db, agent, actor_user_id=user_id)
        binding = await self._find_binding(db, agent_id=agent.id, kind="skill", skill_id=skill_id)
        if binding is None:
            raise_asset_not_found("AGENT_SKILL_NOT_FOUND")
        binding.status = "unbound"
        binding.unbound_at = datetime.now(UTC)
        await db.flush()
        await self._record_version(db, binding, action="unbound", actor_user_id=user_id)
        await self._sync_agent_config_from_bindings(db, agent)
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
        await self._materialize_legacy_bindings(db, agent, actor_user_id=user_id)
        binding = await self._find_binding(db, agent_id=agent.id, kind="skill", skill_id=skill_id)
        if binding is None:
            raise_asset_not_found("AGENT_SKILL_NOT_FOUND")
        if name is not None:
            binding.name = _short_text(name) or binding.name
        if description is not None:
            binding.description = _short_text(description, max_len=240) or binding.description
        await db.flush()
        await self._record_version(db, binding, action="updated", actor_user_id=user_id)
        await self._sync_agent_config_from_bindings(db, agent)
        upload = await _required_upload(db, binding.upload_id)
        return agent, self._skill_out(binding, upload)

    async def record_usage(
        self,
        db: AsyncSession,
        *,
        binding: AgentAssetBinding | None,
        agent: Agent,
        upload: Upload | None,
        event_type: str,
        status_: str,
        reason: str | None = None,
        conversation_id: UUID | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not agent.user_id:
            return
        db.add(
            AgentAssetUsageEvent(
                binding_id=binding.id if binding else None,
                agent_id=agent.id,
                upload_id=upload.id if upload else None,
                conversation_id=conversation_id,
                run_id=run_id,
                event_type=event_type,
                status=status_,
                reason=reason,
                metadata_=metadata or {},
            )
        )
        await db.flush()

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

    async def _assets_out(self, db: AsyncSession, agent: Agent) -> AgentAssetsOut:
        bindings = await self._active_bindings(db, agent.id)
        knowledge: list[AgentKnowledgeOut] = []
        skills: list[AgentSkillOut] = []
        binding_outputs: list[AgentAssetBindingOut] = []
        for binding in bindings:
            upload = await _required_upload(db, binding.upload_id)
            binding_outputs.append(self._binding_out(binding, upload))
            if binding.kind == "knowledge":
                knowledge.append(self._knowledge_out(binding, upload))
            elif binding.kind == "skill":
                skills.append(self._skill_out(binding, upload))
        return AgentAssetsOut(knowledge=knowledge, skills=skills, bindings=binding_outputs)

    async def _sync_agent_config_from_bindings(self, db: AsyncSession, agent: Agent) -> None:
        assets = await self._assets_out(db, agent)
        config = _config_copy(agent)
        config["knowledge"] = [item.model_dump(mode="json") for item in assets.knowledge]
        config["skills"] = [item.model_dump(mode="json") for item in assets.skills]
        agent.config = config
        flag_modified(agent, "config")
        await db.flush()

    async def _materialize_legacy_bindings(
        self,
        db: AsyncSession,
        agent: Agent,
        *,
        actor_user_id: UUID | None,
    ) -> None:
        if not agent.user_id:
            return
        config = _config_copy(agent)
        created = False
        for entry in _list_config_items(config, "knowledge"):
            binding = await self._legacy_knowledge_binding(db, agent, entry)
            if binding is not None:
                await self._record_version(
                    db,
                    binding,
                    action="materialized",
                    actor_user_id=actor_user_id,
                )
                created = True
        for entry in _list_config_items(config, "skills"):
            binding = await self._legacy_skill_binding(db, agent, entry)
            if binding is not None:
                await self._record_version(
                    db,
                    binding,
                    action="materialized",
                    actor_user_id=actor_user_id,
                )
                created = True
        if created:
            await self._sync_agent_config_from_bindings(db, agent)

    async def _legacy_knowledge_binding(
        self,
        db: AsyncSession,
        agent: Agent,
        entry: dict[str, Any],
    ) -> AgentAssetBinding | None:
        upload_id = _coerce_uuid(entry.get("upload_id"))
        if upload_id is None:
            return None
        existing = await self._find_any_binding(
            db,
            agent_id=agent.id,
            kind="knowledge",
            upload_id=upload_id,
        )
        if existing:
            return None
        upload = await _safe_asset_upload(db, agent, upload_id)
        if upload is None:
            return None
        binding = AgentAssetBinding(
            agent_id=agent.id,
            upload_id=upload.id,
            owner_user_id=agent.user_id,
            kind="knowledge",
            status="active",
            label=_short_text(str(entry.get("label") or upload.filename)) or upload.filename,
            usage=_valid_usage(entry.get("usage")),
            metadata_={},
        )
        db.add(binding)
        await db.flush()
        return binding

    async def _legacy_skill_binding(
        self,
        db: AsyncSession,
        agent: Agent,
        entry: dict[str, Any],
    ) -> AgentAssetBinding | None:
        upload_id = _coerce_uuid(entry.get("upload_id"))
        if upload_id is None:
            return None
        skill_id = _short_text(str(entry.get("skill_id") or f"skill_{uuid4().hex}"), max_len=96)
        if skill_id and await self._find_any_binding(
            db, agent_id=agent.id, kind="skill", skill_id=skill_id
        ):
            return None
        if await self._find_any_binding(db, agent_id=agent.id, kind="skill", upload_id=upload_id):
            return None
        upload = await _safe_asset_upload(db, agent, upload_id)
        if upload is None:
            return None
        binding = AgentAssetBinding(
            agent_id=agent.id,
            upload_id=upload.id,
            owner_user_id=agent.user_id,
            kind="skill",
            status="active",
            skill_id=skill_id or f"skill_{uuid4().hex}",
            name=_short_text(str(entry.get("name") or Path(upload.filename).stem))
            or upload.filename,
            description=_short_text(
                str(entry.get("description") or "Uploaded Agent skill."),
                max_len=240,
            )
            or "Uploaded Agent skill.",
            metadata_=entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
        )
        db.add(binding)
        await db.flush()
        return binding

    async def _active_bindings(
        self,
        db: AsyncSession,
        agent_id: str,
        *,
        kind: str | None = None,
    ) -> list[AgentAssetBinding]:
        stmt = select(AgentAssetBinding).where(
            AgentAssetBinding.agent_id == agent_id,
            AgentAssetBinding.status == "active",
        )
        if kind:
            stmt = stmt.where(AgentAssetBinding.kind == kind)
        result = await db.execute(
            stmt.order_by(AgentAssetBinding.created_at.asc(), AgentAssetBinding.id.asc())
        )
        return list(result.scalars())

    async def _find_binding(
        self,
        db: AsyncSession,
        *,
        agent_id: str,
        kind: str,
        upload_id: UUID | None = None,
        skill_id: str | None = None,
    ) -> AgentAssetBinding | None:
        stmt = select(AgentAssetBinding).where(
            AgentAssetBinding.agent_id == agent_id,
            AgentAssetBinding.kind == kind,
            AgentAssetBinding.status == "active",
        )
        if upload_id is not None:
            stmt = stmt.where(AgentAssetBinding.upload_id == upload_id)
        if skill_id is not None:
            stmt = stmt.where(AgentAssetBinding.skill_id == skill_id)
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _find_any_binding(
        self,
        db: AsyncSession,
        *,
        agent_id: str,
        kind: str,
        upload_id: UUID | None = None,
        skill_id: str | None = None,
    ) -> AgentAssetBinding | None:
        stmt = select(AgentAssetBinding).where(
            AgentAssetBinding.agent_id == agent_id,
            AgentAssetBinding.kind == kind,
        )
        if upload_id is not None:
            stmt = stmt.where(AgentAssetBinding.upload_id == upload_id)
        if skill_id is not None:
            stmt = stmt.where(AgentAssetBinding.skill_id == skill_id)
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _record_version(
        self,
        db: AsyncSession,
        binding: AgentAssetBinding,
        *,
        action: str,
        actor_user_id: UUID | None,
    ) -> None:
        version = (
            await db.execute(
                select(func.count(AgentAssetVersion.id)).where(
                    AgentAssetVersion.binding_id == binding.id
                )
            )
        ).scalar_one() + 1
        upload = await _required_upload(db, binding.upload_id)
        db.add(
            AgentAssetVersion(
                binding_id=binding.id,
                version=version,
                action=action,
                snapshot=self._snapshot(binding, upload),
                actor_user_id=actor_user_id,
            )
        )
        await db.flush()

    def _knowledge_out(self, binding: AgentAssetBinding, upload: Upload) -> AgentKnowledgeOut:
        return AgentKnowledgeOut(
            upload_id=upload.id,
            filename=upload.filename,
            label=binding.label or upload.filename,
            usage=_valid_usage(binding.usage),
            content_type=upload.detected_content_type or upload.content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            created_at=binding.created_at or upload.created_at,
        )

    def _skill_out(self, binding: AgentAssetBinding, upload: Upload) -> AgentSkillOut:
        return AgentSkillOut(
            skill_id=binding.skill_id or f"skill_{upload.id.hex}",
            upload_id=upload.id,
            name=binding.name or Path(upload.filename).stem or "Uploaded Skill",
            description=binding.description or "用户上传的 Agent skill。",
            filename=upload.filename,
            content_type=upload.detected_content_type or upload.content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            created_at=binding.created_at or upload.created_at,
            metadata=binding.metadata_ or {},
        )

    def _skill_out_from_upload(
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

    def _binding_out(self, binding: AgentAssetBinding, upload: Upload) -> AgentAssetBindingOut:
        return AgentAssetBindingOut(
            id=binding.id,
            agent_id=binding.agent_id,
            kind=binding.kind,
            status=binding.status,
            upload_id=upload.id,
            filename=upload.filename,
            content_type=upload.detected_content_type or upload.content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            label=binding.label,
            usage=_valid_usage(binding.usage) if binding.kind == "knowledge" else None,
            skill_id=binding.skill_id,
            name=binding.name,
            description=binding.description,
            metadata=binding.metadata_ or {},
            created_at=binding.created_at,
            updated_at=binding.updated_at,
            unbound_at=binding.unbound_at,
        )

    def _version_out(self, version: AgentAssetVersion) -> AgentAssetVersionOut:
        return AgentAssetVersionOut(
            id=version.id,
            binding_id=version.binding_id,
            version=version.version,
            action=version.action,
            snapshot=version.snapshot or {},
            actor_user_id=version.actor_user_id,
            created_at=version.created_at,
        )

    def _usage_out(self, event: AgentAssetUsageEvent) -> AgentAssetUsageEventOut:
        return AgentAssetUsageEventOut(
            id=event.id,
            binding_id=event.binding_id,
            agent_id=event.agent_id,
            upload_id=event.upload_id,
            conversation_id=event.conversation_id,
            run_id=event.run_id,
            event_type=event.event_type,
            status=event.status,
            reason=event.reason,
            metadata=event.metadata_ or {},
            created_at=event.created_at,
        )

    def _snapshot(self, binding: AgentAssetBinding, upload: Upload) -> dict[str, Any]:
        return {
            "binding_id": str(binding.id),
            "agent_id": binding.agent_id,
            "kind": binding.kind,
            "status": binding.status,
            "upload_id": str(upload.id),
            "filename": upload.filename,
            "content_type": upload.detected_content_type or upload.content_type,
            "size_bytes": upload.size_bytes,
            "sha256": upload.sha256,
            "label": binding.label,
            "usage": binding.usage,
            "skill_id": binding.skill_id,
            "name": binding.name,
            "description": binding.description,
            "metadata": binding.metadata_ or {},
            "unbound_at": binding.unbound_at.isoformat() if binding.unbound_at else None,
        }

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


def _coerce_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
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


def _valid_usage(value: object) -> AgentKnowledgeUsage:
    if value in {"reference", "policy", "template", "example"}:
        return cast(AgentKnowledgeUsage, value)
    return "reference"


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
    conversation_id: UUID | None = None,
    run_id: str | None = None,
) -> str:
    """Build bounded prompt context from user-approved custom Agent assets."""
    if not agent.user_id:
        return ""
    if not hasattr(db, "execute"):
        return await _legacy_agent_asset_context(db, agent, max_chars=max_chars)
    try:
        await agent_asset_service._materialize_legacy_bindings(
            db,
            agent,
            actor_user_id=None,
        )
        bindings = await agent_asset_service._active_bindings(db, agent.id)
    except Exception as exc:  # pragma: no cover - fallback for pre-migration deployments.
        logger.warning("Falling back to legacy agent asset config context: %s", exc)
        return await _legacy_agent_asset_context(db, agent, max_chars=max_chars)

    sections: list[str] = []
    knowledge = await _binding_context(
        db,
        agent,
        [item for item in bindings if item.kind == "knowledge"],
        conversation_id=conversation_id,
        run_id=run_id,
    )
    if knowledge:
        sections.append("## Agent Knowledge\n" + "\n\n".join(knowledge))
    skills = await _binding_context(
        db,
        agent,
        [item for item in bindings if item.kind == "skill"],
        conversation_id=conversation_id,
        run_id=run_id,
    )
    if skills:
        sections.append("## Agent Skills\n" + "\n\n".join(skills))
    return _format_asset_context(sections, max_chars=max_chars)


def append_agent_asset_context(system_prompt: str | None, asset_context: str) -> str | None:
    if not asset_context:
        return system_prompt
    base = (system_prompt or "").strip()
    section = f"<agent_uploaded_assets>\n{asset_context}\n</agent_uploaded_assets>"
    return f"{base}\n\n{section}" if base else section


async def _legacy_agent_asset_context(
    db: AsyncSession,
    agent: Agent,
    *,
    max_chars: int,
) -> str:
    config = _config_copy(agent)
    sections: list[str] = []
    knowledge = await _legacy_knowledge_context(db, agent, _list_config_items(config, "knowledge"))
    if knowledge:
        sections.append("## Agent Knowledge\n" + "\n\n".join(knowledge))
    skills = await _legacy_skill_context(db, agent, _list_config_items(config, "skills"))
    if skills:
        sections.append("## Agent Skills\n" + "\n\n".join(skills))
    return _format_asset_context(sections, max_chars=max_chars)


def _format_asset_context(sections: list[str], *, max_chars: int) -> str:
    if not sections:
        return ""
    context = (
        "The user explicitly attached the following custom Agent assets. "
        "Use them when relevant and do not assume unavailable files contain more than shown.\n\n"
        + "\n\n".join(sections)
    )
    return context[:max_chars]


async def _binding_context(
    db: AsyncSession,
    agent: Agent,
    bindings: list[AgentAssetBinding],
    *,
    conversation_id: UUID | None,
    run_id: str | None,
) -> list[str]:
    lines: list[str] = []
    for binding in bindings:
        upload = await _safe_asset_upload(db, agent, binding.upload_id)
        if upload is None:
            await _record_usage_safely(
                db,
                binding=binding,
                agent=agent,
                upload=None,
                status_="skipped",
                reason="upload_unavailable",
                conversation_id=conversation_id,
                run_id=run_id,
            )
            continue
        content = _read_upload_text(upload)
        if not content:
            await _record_usage_safely(
                db,
                binding=binding,
                agent=agent,
                upload=upload,
                status_="skipped",
                reason="empty_content",
                conversation_id=conversation_id,
                run_id=run_id,
            )
            continue
        lines.append(_context_line(binding, upload, content))
        await _record_usage_safely(
            db,
            binding=binding,
            agent=agent,
            upload=upload,
            status_="injected",
            conversation_id=conversation_id,
            run_id=run_id,
            metadata={"chars": len(content), "kind": binding.kind},
        )
    return lines


def _context_line(binding: AgentAssetBinding, upload: Upload, content: str) -> str:
    if binding.kind == "skill":
        name = binding.name or Path(upload.filename).stem or upload.filename
        description = binding.description or "Uploaded Agent skill."
        return f"### {name}\n- file: {upload.filename}\n- description: {description}\n\n{content}"
    label = binding.label or upload.filename
    usage = _valid_usage(binding.usage)
    return f"### {label}\n- file: {upload.filename}\n- usage: {usage}\n\n{content}"


async def _record_usage_safely(
    db: AsyncSession,
    *,
    binding: AgentAssetBinding | None,
    agent: Agent,
    upload: Upload | None,
    status_: str,
    reason: str | None = None,
    conversation_id: UUID | None = None,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        await agent_asset_service.record_usage(
            db,
            binding=binding,
            agent=agent,
            upload=upload,
            event_type="context_injection",
            status_=status_,
            reason=reason,
            conversation_id=conversation_id,
            run_id=run_id,
            metadata=metadata,
        )
    except Exception as exc:  # pragma: no cover - telemetry must not break chat.
        logger.warning("Failed to record agent asset usage: %s", exc)


async def _legacy_knowledge_context(
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


async def _legacy_skill_context(
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
    parsed = _coerce_uuid(upload_id)
    if parsed is None:
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


async def _required_upload(db: AsyncSession, upload_id: UUID) -> Upload:
    upload = await db.get(Upload, upload_id)
    if upload is None:
        raise_asset_not_found("AGENT_ASSET_UPLOAD_NOT_FOUND")
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
