"""FastAPI dependency exposing the async Redis client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.redis.client import redis_manager

if TYPE_CHECKING:
    from redis.asyncio import Redis


def get_redis() -> Redis:
    """Return the active async Redis client. Raises if not initialised."""
    return redis_manager.client


__all__ = ["get_redis"]
