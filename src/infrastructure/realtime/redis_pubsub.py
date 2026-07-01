"""Redis pub/sub helpers for real-time user notifications."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from src.core.logging import get_logger

logger = get_logger(__name__)

_CHANNEL_PREFIX = "notifications:user:"


def user_notification_channel(user_id: UUID) -> str:
    return f"{_CHANNEL_PREFIX}{user_id}"


class NotificationRealtimePublisher:
    """Publishes notification events to per-user Redis channels."""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def publish_user_notification(
        self, user_id: UUID, payload: dict[str, Any]
    ) -> None:
        channel = user_notification_channel(user_id)
        message = json.dumps({"type": "notification", "data": payload})
        await self._redis.publish(channel, message)
        logger.debug("notification_published", user_id=str(user_id))


async def subscribe_user_notifications(
    redis_client: Redis, user_id: UUID
) -> AsyncIterator[dict[str, Any]]:
    """Yield parsed notification events from a user's Redis pub/sub channel."""
    channel = user_notification_channel(user_id)
    # Dedicated connection — pub/sub must not share the pool connection used for publish.
    dedicated = redis_client.duplicate()
    pubsub = dedicated.pubsub()
    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message is None:
                yield {"type": "ping"}
                continue
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if data is None:
                continue
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if not isinstance(data, str):
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("notification_sse_invalid_json", user_id=str(user_id))
                continue
            if isinstance(parsed, dict):
                yield parsed
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await dedicated.aclose()


__all__ = [
    "NotificationRealtimePublisher",
    "subscribe_user_notifications",
    "user_notification_channel",
]
