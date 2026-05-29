"""MongoDB connection lifecycle.

Uses the native PyMongo Async API (``pymongo.AsyncMongoClient``).
Motor reached end of life on 14-May-2026 — the async PyMongo client is
the official replacement and is GA since PyMongo 4.9.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi

from src.core.config import Settings, get_settings
from src.core.exceptions import ExternalServiceError
from src.core.logging import get_logger

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase

logger = get_logger(__name__)


class MongoClientManager:
    """Owns the async MongoDB client and exposes safe accessors.

    Lifecycle is driven by the FastAPI ``lifespan`` context. Outside of tests,
    a single instance is shared process-wide via the module-level ``mongo``.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: AsyncMongoClient | None = None
        self._db: AsyncDatabase | None = None

    # -------------------------------------------------------------- lifecycle
    async def connect(self) -> None:
        if self._client is not None:
            return

        logger.info(
            "mongo_connecting",
            uri_host=self._settings.MONGO_URI.split("@")[-1].split("/")[0],
            db=self._settings.MONGO_DB,
        )

        self._client = AsyncMongoClient(
            self._settings.MONGO_URI,
            uuidRepresentation="standard",
            tz_aware=True,
            minPoolSize=self._settings.MONGO_MIN_POOL_SIZE,
            maxPoolSize=self._settings.MONGO_MAX_POOL_SIZE,
            serverSelectionTimeoutMS=self._settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
            server_api=ServerApi("1"),
            appname=self._settings.APP_NAME,
        )

        try:
            await self._client.admin.command("ping")
        except Exception as exc:  # noqa: BLE001 — re-raised as domain error
            logger.error("mongo_connection_failed", error=str(exc))
            await self._client.close()
            self._client = None
            raise ExternalServiceError(
                "Failed to connect to MongoDB.",
                code="mongo_unavailable",
            ) from exc

        self._db = self._client[self._settings.MONGO_DB]
        logger.info("mongo_connected", db=self._settings.MONGO_DB)

    async def close(self) -> None:
        if self._client is None:
            return
        logger.info("mongo_closing")
        await self._client.close()
        self._client = None
        self._db = None

    # ---------------------------------------------------------------- access
    @property
    def client(self) -> AsyncMongoClient:
        if self._client is None:
            raise RuntimeError("MongoDB client not initialised; call connect() first.")
        return self._client

    @property
    def db(self) -> AsyncDatabase:
        if self._db is None:
            raise RuntimeError("MongoDB database not initialised; call connect() first.")
        return self._db

    def get_collection(self, name: str) -> AsyncCollection:
        return self.db[name]

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.admin.command("ping")
        except Exception:  # noqa: BLE001
            return False
        return True


mongo = MongoClientManager()
"""Process-wide singleton — connect/close in the FastAPI lifespan."""


__all__ = ["MongoClientManager", "mongo"]
