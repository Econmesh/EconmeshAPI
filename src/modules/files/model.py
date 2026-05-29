"""Persistence model for ``files``."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument


class FileDocument(DomainDocument):
    """Metadata about a file stored in the object-storage provider."""

    collection_name: ClassVar[str] = "files"

    storage_key: str = Field(..., description="Object key in the storage backend.")
    filename: str
    content_type: str
    size_bytes: int = Field(..., ge=0)
    sha256: str | None = None
    owner_user_id: UUID
    company_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)


__all__ = ["FileDocument"]
