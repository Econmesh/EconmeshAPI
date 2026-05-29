"""Asynchronous messaging abstraction.

Backends to swap in later: RabbitMQ (aio-pika), Kafka (aiokafka),
Redis Streams, Google Pub/Sub, etc. The contract is intentionally
minimal — publish + subscribe — to keep adapters independent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Headers = dict[str, str]
MessageHandler = Callable[["Message"], Awaitable[None]]


@dataclass(slots=True, frozen=True)
class Message:
    """A queue message envelope."""

    topic: str
    body: dict[str, Any]
    headers: Headers
    message_id: str


class QueueProvider(ABC):
    """Async pub/sub contract."""

    @abstractmethod
    async def publish(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        headers: Headers | None = None,
        key: str | None = None,
    ) -> str:
        """Publish a message and return its ID."""

    @abstractmethod
    async def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Yield messages from ``topic`` until cancelled."""

    @abstractmethod
    async def ack(self, message: Message) -> None:
        """Acknowledge successful processing."""

    @abstractmethod
    async def nack(self, message: Message, *, requeue: bool = True) -> None:
        """Negative acknowledgement — optionally requeue for retry."""


__all__ = ["Message", "MessageHandler", "QueueProvider"]
