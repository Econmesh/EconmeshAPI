"""Business rules for ``files``. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.files.repository import FilesRepository
from src.modules.files.schema import (
    FileMetadataResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)


class FilesService:
    def __init__(self, repository: FilesRepository) -> None:
        self._repo = repository
        # TODO: inject a StorageProvider implementation (S3/GCS/local).

    async def list_for_owner(
        self, owner_user_id: UUID, *, page: int, page_size: int
    ) -> list[FileMetadataResponse]:
        raise NotImplementedError("TODO: list files owned by user")

    async def get(self, file_id: UUID) -> FileMetadataResponse:
        raise NotImplementedError("TODO: fetch file metadata")

    async def request_upload(
        self, owner_user_id: UUID, payload: PresignedUploadRequest
    ) -> PresignedUploadResponse:
        # TODO: presign PUT on the storage backend + persist pending metadata.
        raise NotImplementedError

    async def delete(self, file_id: UUID) -> None:
        # TODO: delete storage object + metadata
        raise NotImplementedError


__all__ = ["FilesService"]
