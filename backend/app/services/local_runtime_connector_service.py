"""Local runtime connector registration service."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_refresh_token
from app.models.session import LocalRuntimeConnector
from app.schemas.local_runtime_connector import (
    LocalRuntimeConnectorOut,
    LocalRuntimeConnectorStatusOut,
    RegisterLocalRuntimeConnectorRequest,
)
from app.services.audit_service import record_audit_event


class LocalRuntimeConnectorService:
    async def status(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
    ) -> LocalRuntimeConnectorStatusOut:
        connectors = await self.list_connectors(db, user_id=user_id)
        return LocalRuntimeConnectorStatusOut(
            enabled=settings.agenthub_deployment_mode == "local",
            deployment_mode=settings.agenthub_deployment_mode,
            connectors=[self.to_out(connector) for connector in connectors],
        )

    async def list_connectors(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
    ) -> list[LocalRuntimeConnector]:
        stmt = (
            select(LocalRuntimeConnector)
            .where(LocalRuntimeConnector.user_id == user_id)
            .order_by(LocalRuntimeConnector.created_at.desc())
        )
        return list((await db.execute(stmt)).scalars().all())

    async def register(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        payload: RegisterLocalRuntimeConnectorRequest,
    ) -> LocalRuntimeConnector:
        self._assert_local_deployment()
        self._assert_loopback(payload.endpoint_url)
        connector = LocalRuntimeConnector(
            user_id=user_id,
            name=payload.name,
            endpoint_url=payload.endpoint_url,
            token_hash=hash_refresh_token(payload.bearer_token),
            capabilities=payload.capabilities,
            runtime_ids=payload.runtime_ids,
            status="ready",
            last_seen_at=datetime.now(UTC),
            expires_at=payload.expires_at,
        )
        db.add(connector)
        await db.flush()
        await record_audit_event(
            db,
            user_id=user_id,
            action="local_runtime_connector.registered",
            resource_type="local_runtime_connector",
            resource_id=connector.id,
            metadata={"runtime_ids": connector.runtime_ids},
        )
        return connector

    async def revoke(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        connector_id: UUID,
    ) -> LocalRuntimeConnector:
        connector = await db.get(LocalRuntimeConnector, connector_id)
        if connector is None or connector.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "LOCAL_RUNTIME_CONNECTOR_NOT_FOUND",
                        "message": "Connector not found",
                    }
                },
            )
        connector.status = "revoked"
        connector.revoked_at = datetime.now(UTC)
        await record_audit_event(
            db,
            user_id=user_id,
            action="local_runtime_connector.revoked",
            resource_type="local_runtime_connector",
            resource_id=connector.id,
        )
        return connector

    def to_out(self, connector: LocalRuntimeConnector) -> LocalRuntimeConnectorOut:
        status_value = connector.status
        if (
            status_value == "ready"
            and connector.expires_at
            and connector.expires_at <= datetime.now(UTC)
        ):
            status_value = "unavailable"
        return LocalRuntimeConnectorOut(
            id=connector.id,
            name=connector.name,
            endpoint_url=connector.endpoint_url,
            status=status_value,  # type: ignore[arg-type]
            runtime_ids=connector.runtime_ids,
            capabilities=connector.capabilities,
            created_at=connector.created_at,
            last_seen_at=connector.last_seen_at,
            expires_at=connector.expires_at,
            revoked_at=connector.revoked_at,
            last_error=connector.last_error,
        )

    def _assert_local_deployment(self) -> None:
        if settings.agenthub_deployment_mode != "local":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "LOCAL_RUNTIME_CONNECTOR_DISABLED",
                        "message": "Local runtime connectors are only available for local backends",
                    }
                },
            )

    def _assert_loopback(self, endpoint_url: str) -> None:
        parsed = urlparse(endpoint_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "INVALID_CONNECTOR_ENDPOINT",
                        "message": "Connector endpoint must be an HTTP loopback URL",
                    }
                },
            )


local_runtime_connector_service = LocalRuntimeConnectorService()
