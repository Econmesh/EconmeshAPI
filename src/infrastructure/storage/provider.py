"""Object-storage abstraction.

Concrete implementations (local filesystem, S3, GCS, Azure Blob) live in
``infrastructure/storage/<provider>.py`` and implement ``StorageProvider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class StoredObject:
    """Metadata describing an object held in a storage backend."""

    key: str
    url: str
    size_bytes: int
    content_type: str | None = None
    etag: str | None = None


class StorageProvider(ABC):
    """Async storage contract — keep implementations side-effect-free at import time."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        """Upload a blob and return its metadata."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download a blob by key."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove a blob by key (idempotent)."""

    @abstractmethod
    async def presign_get(self, key: str, *, expires_in: int = 3_600) -> str:
        """Return a time-limited URL for direct download by a client."""

    @abstractmethod
    async def presign_put(
        self, key: str, *, expires_in: int = 3_600, content_type: str | None = None
    ) -> str:
        """Return a time-limited URL for direct upload by a client."""


__all__ = ["StorageProvider", "StoredObject"]
