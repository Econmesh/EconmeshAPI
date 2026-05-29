"""HTTP controller for ``files``. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.files.schema import (
    FileMetadataResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from src.modules.files.service import FilesService


class FilesController:
    def __init__(self, service: FilesService) -> None:
        self._service = service

    async def list_for_owner(
        self, owner_user_id: UUID, page: int, page_size: int
    ) -> list[FileMetadataResponse]:
        return await self._service.list_for_owner(
            owner_user_id, page=page, page_size=page_size
        )

    async def get(self, file_id: UUID) -> FileMetadataResponse:
        return await self._service.get(file_id)

    async def request_upload(
        self, owner_user_id: UUID, payload: PresignedUploadRequest
    ) -> PresignedUploadResponse:
        return await self._service.request_upload(owner_user_id, payload)


__all__ = ["FilesController"]
