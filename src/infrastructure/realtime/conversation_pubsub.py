"""Redis pub/sub helpers for real-time opportunity conversation events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from src.core.logging import get_logger

logger = get_logger(__name__)

_USER_CHANNEL_PREFIX = "conversation:user:"
_ADMIN_CHANNEL = "conversation:admin"
_THREAD_CHANNEL_PREFIX = "conversation:thread:"


def conversation_user_channel(user_id: UUID) -> str:
    return f"{_USER_CHANNEL_PREFIX}{user_id}"


def conversation_admin_channel() -> str:
    return _ADMIN_CHANNEL


def conversation_thread_channel(conversation_id: UUID) -> str:
    return f"{_THREAD_CHANNEL_PREFIX}{conversation_id}"


class ConversationRealtimePublisher:
    """Publishes conversation events to Redis channels."""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def _publish(self, channel: str, event_type: str, data: dict[str, Any]) -> None:
        message = json.dumps({"type": event_type, "data": data})
        await self._redis.publish(channel, message)
        logger.debug(
            "conversation_event_published", channel=channel, event_type=event_type
        )

    async def publish_to_user(self, user_id: UUID, event_type: str, data: dict[str, Any]) -> None:
        await self._publish(conversation_user_channel(user_id), event_type, data)

    async def publish_to_admins(self, event_type: str, data: dict[str, Any]) -> None:
        await self._publish(conversation_admin_channel(), event_type, data)

    async def publish_to_thread(
        self, conversation_id: UUID, event_type: str, data: dict[str, Any]
    ) -> None:
        await self._publish(
            conversation_thread_channel(conversation_id), event_type, data
        )


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
                logger.warning("conversation_sse_invalid_json", channel=channel)
                continue
            if isinstance(parsed, dict):
                yield parsed
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await dedicated.aclose()


async def subscribe_conversation_user(
    redis_client: Redis, user_id: UUID
) -> AsyncIterator[dict[str, Any]]:
    async for event in _subscribe_channel(
        redis_client, conversation_user_channel(user_id)
    ):
        yield event


async def subscribe_conversation_admin(
    redis_client: Redis,
) -> AsyncIterator[dict[str, Any]]:
    async for event in _subscribe_channel(redis_client, conversation_admin_channel()):
        yield event


async def subscribe_conversation_thread(
    redis_client: Redis, conversation_id: UUID
) -> AsyncIterator[dict[str, Any]]:
    async for event in _subscribe_channel(
        redis_client, conversation_thread_channel(conversation_id)
    ):
        yield event


__all__ = [
    "ConversationRealtimePublisher",
    "conversation_admin_channel",
    "conversation_thread_channel",
    "conversation_user_channel",
    "subscribe_conversation_admin",
    "subscribe_conversation_thread",
    "subscribe_conversation_user",
]
