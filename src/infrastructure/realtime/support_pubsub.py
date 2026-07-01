"""Redis pub/sub helpers for real-time support ticket events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from src.core.logging import get_logger

logger = get_logger(__name__)

_USER_CHANNEL_PREFIX = "support:user:"
_ADMIN_CHANNEL = "support:admin"
_TICKET_CHANNEL_PREFIX = "support:ticket:"


def support_user_channel(user_id: UUID) -> str:
    return f"{_USER_CHANNEL_PREFIX}{user_id}"


def support_admin_channel() -> str:
    return _ADMIN_CHANNEL


def support_ticket_channel(ticket_id: UUID) -> str:
    return f"{_TICKET_CHANNEL_PREFIX}{ticket_id}"


class SupportRealtimePublisher:
    """Publishes support events to Redis channels."""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def _publish(self, channel: str, event_type: str, data: dict[str, Any]) -> None:
        message = json.dumps({"type": event_type, "data": data})
        await self._redis.publish(channel, message)
        logger.debug("support_event_published", channel=channel, event_type=event_type)

    async def publish_to_user(self, user_id: UUID, event_type: str, data: dict[str, Any]) -> None:
        await self._publish(support_user_channel(user_id), event_type, data)

    async def publish_to_admins(self, event_type: str, data: dict[str, Any]) -> None:
        await self._publish(support_admin_channel(), event_type, data)

    async def publish_to_ticket(
        self, ticket_id: UUID, event_type: str, data: dict[str, Any]
    ) -> None:
        await self._publish(support_ticket_channel(ticket_id), event_type, data)


async def _subscribe_channel(
    redis_client: Redis, channel: str
) -> AsyncIterator[dict[str, Any]]:
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
                logger.warning("support_sse_invalid_json", channel=channel)
                continue
            if isinstance(parsed, dict):
                yield parsed
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await dedicated.aclose()


async def subscribe_support_user(
    redis_client: Redis, user_id: UUID
) -> AsyncIterator[dict[str, Any]]:
    async for event in _subscribe_channel(redis_client, support_user_channel(user_id)):
        yield event


async def subscribe_support_admin(redis_client: Redis) -> AsyncIterator[dict[str, Any]]:
    async for event in _subscribe_channel(redis_client, support_admin_channel()):
        yield event


async def subscribe_support_ticket(
    redis_client: Redis, ticket_id: UUID
) -> AsyncIterator[dict[str, Any]]:
    async for event in _subscribe_channel(
        redis_client, support_ticket_channel(ticket_id)
    ):
        yield event


__all__ = [
    "SupportRealtimePublisher",
    "subscribe_support_admin",
    "subscribe_support_ticket",
    "subscribe_support_user",
    "support_admin_channel",
    "support_ticket_channel",
    "support_user_channel",
]
