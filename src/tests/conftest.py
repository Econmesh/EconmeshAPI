"""Shared pytest fixtures.

The fixtures here avoid touching real external services. Tests that need a
running Mongo/Redis are marked with ``@pytest.mark.integration`` and skipped
by default in CI unless the appropriate env vars are set.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest

# Force the TEST environment BEFORE importing settings, so the lru_cache picks it up.
os.environ.setdefault("ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("ENABLE_DOCS", "false")
os.environ.setdefault("FIREBASE_PROJECT_ID", "econmesh-test")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "econmesh_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault(
    "DATA_ENCRYPTION_KEY",
    "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
)

from asgi_lifespan import LifespanManager  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import mongo  # noqa: E402
from src.core.firebase import firebase  # noqa: E402
from src.infrastructure.redis.client import redis_manager  # noqa: E402


# ---------------------------------------------------------------------------
# Settings / app fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """Build a fresh FastAPI app with external resources stubbed."""

    # --- Stub Mongo --------------------------------------------------------
    # MagicMock supports __getitem__, so ``fake_db["users"]`` returns another
    # mock collection — enough for repositories that only need a reference.
    fake_db = MagicMock(name="FakeMongoDatabase")

    async def _noop_connect() -> None:
        return None

    async def _noop_close() -> None:
        return None

    async def _ping_ok() -> bool:
        return True

    monkeypatch.setattr(mongo, "connect", _noop_connect)
    monkeypatch.setattr(mongo, "close", _noop_close)
    monkeypatch.setattr(mongo, "ping", _ping_ok)
    monkeypatch.setattr(type(mongo), "db", property(lambda self: fake_db), raising=False)

    # --- Stub Redis --------------------------------------------------------
    fake_redis = AsyncMock()
    fake_redis.ping = AsyncMock(return_value=True)
    fake_redis.delete = AsyncMock(return_value=1)
    fake_redis.set = AsyncMock(return_value=True)
    fake_redis.exists = AsyncMock(return_value=0)
    fake_redis.hset = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock(return_value=True)
    fake_redis.aclose = AsyncMock()

    monkeypatch.setattr(redis_manager, "connect", _noop_connect)
    monkeypatch.setattr(redis_manager, "close", _noop_close)
    monkeypatch.setattr(redis_manager, "ping", _ping_ok)
    monkeypatch.setattr(
        type(redis_manager), "client", property(lambda self: fake_redis), raising=False
    )

    # --- Stub Firebase -----------------------------------------------------
    monkeypatch.setattr(firebase, "init", lambda: None)
    monkeypatch.setattr(firebase, "shutdown", lambda: None)

    # Import the factory AFTER the patches so the lifespan uses them.
    from src.main import create_app

    application = create_app()
    yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # ``LifespanManager`` drives the FastAPI startup/shutdown hooks that
    # ``httpx.AsyncClient`` would otherwise skip when called over ASGI directly.
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
