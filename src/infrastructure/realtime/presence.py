"""Redis-backed user presence (online/offline)."""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

_PRESENCE_PREFIX = "presence:user:"
_DEFAULT_TTL_SECONDS = 90


def presence_key(user_id: UUID) -> str:
    return f"{_PRESENCE_PREFIX}{user_id}"


class PresenceService:
    """Tracks whether a user has an active session (SSE or heartbeat)."""

    def __init__(
        self, redis_client: Redis, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    async def touch(self, user_id: UUID) -> None:
        await self._redis.set(presence_key(user_id), "1", ex=self._ttl)

    async def clear(self, user_id: UUID) -> None:
        await self._redis.delete(presence_key(user_id))

    async def is_online(self, user_id: UUID) -> bool:
        return bool(await self._redis.exists(presence_key(user_id)))


__all__ = ["PresenceService", "presence_key"]
