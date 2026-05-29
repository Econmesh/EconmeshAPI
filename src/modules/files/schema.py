"""DTOs for the ``files`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import APIModel


class FileMetadataResponse(APIModel):
    id: UUID
    storage_key: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str | None = None
    owner_user_id: UUID
    company_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PresignedUploadRequest(APIModel):
    filename: str
    content_type: str
    company_id: UUID | None = None


class PresignedUploadResponse(APIModel):
    upload_url: str
    storage_key: str
    expires_at: datetime


__all__ = [
    "FileMetadataResponse",
    "PresignedUploadRequest",
    "PresignedUploadResponse",
]
