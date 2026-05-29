"""Async Redis client lifecycle.

Wraps ``redis.asyncio.Redis`` behind a singleton manager so the FastAPI
lifespan can own its connect/disconnect calls and the rest of the codebase
can treat the client as an injected dependency.
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from src.core.config import Settings, get_settings
from src.core.exceptions import ExternalServiceError
from src.core.logging import get_logger

logger = get_logger(__name__)


class RedisManager:
    """Process-wide async Redis client wrapper."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    # -------------------------------------------------------------- lifecycle
    async def connect(self) -> None:
        if self._client is not None:
            return

        logger.info("redis_connecting", url=self._safe_url())
        self._pool = ConnectionPool.from_url(
            self._settings.REDIS_URL,
            max_connections=self._settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )
        self._client = Redis(connection_pool=self._pool)

        try:
            await self._client.ping()
        except Exception as exc:  # noqa: BLE001
            logger.error("redis_connection_failed", error=str(exc))
            await self.close()
            raise ExternalServiceError(
                "Failed to connect to Redis.",
                code="redis_unavailable",
            ) from exc

        logger.info("redis_connected")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
        logger.info("redis_closed")

    # ---------------------------------------------------------------- access
    @property
    def client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("Redis client not initialised; call connect() first.")
        return self._client

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:  # noqa: BLE001
            return False

    # ---------------------------------------------------------------- helpers
    def _safe_url(self) -> str:
        url = self._settings.REDIS_URL
        if "@" in url:
            scheme, _, rest = url.partition("://")
            _, _, host = rest.partition("@")
            return f"{scheme}://***@{host}"
        return url


redis_manager = RedisManager()
"""Process-wide singleton — connect/close in the FastAPI lifespan."""


__all__ = ["RedisManager", "redis_manager"]
