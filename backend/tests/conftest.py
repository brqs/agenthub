"""Global pytest safety guards."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.engine import make_url

from app.agents.orchestrator.availability import clear_runtime_cooldowns
from app.core.config import settings


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_default_dev_database_url(database_url: str) -> bool:
    try:
        parsed = make_url(database_url)
    except Exception:
        return False
    return (parsed.database or "").rsplit("/", maxsplit=1)[-1] == "agenthub"


def pytest_configure(config: pytest.Config) -> None:
    if _is_truthy(os.getenv("AGENTHUB_ALLOW_DEV_DB_TESTS")):
        return
    database_url = os.getenv("DATABASE_URL") or settings.database_url
    if _is_default_dev_database_url(database_url):
        raise pytest.UsageError(
            "Refusing to run backend tests against the default development database "
            "'agenthub'. Use an isolated test database/schema, or set "
            "AGENTHUB_ALLOW_DEV_DB_TESTS=1 for an intentional one-off run."
        )


@pytest.fixture(autouse=True)
def _clear_orchestrator_runtime_cooldowns() -> None:
    clear_runtime_cooldowns()
    yield
    clear_runtime_cooldowns()
