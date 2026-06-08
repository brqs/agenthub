"""Model account API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.v1 import model_accounts as model_accounts_api
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.model_account import UserModelAccount
from app.models.user import User
from app.services.model_accounts import resolve_agent_model_config

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE name LIKE 'Backpack Test Agent%'"))
        await db.execute(
            text("DELETE FROM user_model_accounts WHERE display_name LIKE 'Backpack%'")
        )
        await db.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> dict[str, str]:
    username = f"model_backpack_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_model_providers_include_free_deepseek(client: AsyncClient) -> None:
    headers = await _register(client)

    response = await client.get("/api/v1/model-providers", headers=headers)

    assert response.status_code == 200, response.text
    providers = {item["provider"]: item for item in response.json()["items"]}
    assert providers["deepseek"]["default_model"] == "deepseek-v4-flash"
    assert providers["openai_compatible"]["requires_base_url"] is True


async def test_model_account_crud_never_returns_api_key(client: AsyncClient) -> None:
    headers = await _register(client)

    create = await client.post(
        "/api/v1/model-accounts",
        headers=headers,
        json={
            "display_name": "Backpack DeepSeek",
            "provider": "deepseek",
            "api_key": "sk-test-secret-1234",
            "model": "deepseek-v4-flash",
        },
    )

    assert create.status_code == 201, create.text
    body = create.json()
    assert body["api_key_preview"] == "sk-***1234"
    assert "api_key" not in body
    assert "encrypted_api_key" not in body

    listing = await client.get("/api/v1/model-accounts", headers=headers)
    assert listing.status_code == 200, listing.text
    assert "sk-test-secret-1234" not in listing.text
    assert listing.json()["items"][0]["api_key_preview"] == "sk-***1234"


async def test_openai_compatible_requires_base_url(client: AsyncClient) -> None:
    headers = await _register(client)

    response = await client.post(
        "/api/v1/model-accounts",
        headers=headers,
        json={
            "display_name": "Backpack Compatible",
            "provider": "openai_compatible",
            "api_key": "sk-compatible",
            "model": "custom-model",
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"]["code"] == "INVALID_MODEL_ACCOUNT"


async def test_delete_account_in_use_returns_409(client: AsyncClient) -> None:
    headers = await _register(client)
    account = await client.post(
        "/api/v1/model-accounts",
        headers=headers,
        json={
            "display_name": "Backpack In Use",
            "provider": "openai",
            "api_key": "sk-openai-1234",
            "model": "gpt-4o-mini",
        },
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]

    agent = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "name": "Backpack Test Agent",
            "provider": "builtin",
            "capabilities": ["custom"],
            "system_prompt": "Use the selected model account.",
            "config": {
                "model_backend": "openai",
                "model_profile": {
                    "source": "user_account",
                    "account_id": account_id,
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                },
                "max_iterations": 4,
                "mcp_servers": [],
            },
        },
    )
    assert agent.status_code == 201, agent.text

    delete = await client.delete(f"/api/v1/model-accounts/{account_id}", headers=headers)

    assert delete.status_code == 409, delete.text
    assert delete.json()["detail"]["error"]["code"] == "MODEL_ACCOUNT_IN_USE"


async def test_verify_account_updates_status(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register(client)
    account = await client.post(
        "/api/v1/model-accounts",
        headers=headers,
        json={
            "display_name": "Backpack Verify",
            "provider": "deepseek",
            "api_key": "sk-verify-1234",
            "model": "deepseek-v4-flash",
        },
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]

    async def fake_verify(account: UserModelAccount) -> tuple[str, str | None]:
        assert account.display_name == "Backpack Verify"
        return "ready", None

    monkeypatch.setattr(model_accounts_api, "verify_model_account", fake_verify)

    response = await client.post(f"/api/v1/model-accounts/{account_id}/verify", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"


async def test_unavailable_model_account_does_not_fall_back_to_global_key() -> None:
    async with SessionFactory() as db:
        user = User(username=f"model_backpack_user_{uuid4().hex[:16]}", password_hash="hash")
        db.add(user)
        await db.flush()
        account = UserModelAccount(
            user_id=user.id,
            display_name="Backpack Unavailable",
            provider="openai",
            protocol="openai_compatible",
            model="gpt-5.4-mini",
            encrypted_api_key="encrypted",
            api_key_preview="sk-***0000",
            status="unavailable",
            last_error="verification failed",
        )
        db.add(account)
        await db.flush()
        agent = Agent(
            id=f"backpack-unavailable-{uuid4().hex[:8]}",
            name="Backpack Test Agent Unavailable",
            provider="builtin",
            user_id=user.id,
            config={
                "model_backend": "openai",
                "model_profile": {
                    "source": "user_account",
                    "account_id": str(account.id),
                    "provider": "openai",
                    "model": "gpt-5.4-mini",
                },
            },
        )

        config = await resolve_agent_model_config(db, agent)

        assert config["_runtime_api_key"] == ""
        assert config["_runtime_model_account_error"] == "verification failed"
        assert config["model_backend"] == "openai"
