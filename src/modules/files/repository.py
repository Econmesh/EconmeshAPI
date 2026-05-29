"""Data access for ``files``. SKELETON."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.modules.files.model import FileDocument

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class FilesRepository:
    COLLECTION: str = FileDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # TODO: indexes on (owner_user_id, created_at), (company_id, created_at), unique (storage_key)
        raise NotImplementedError

    async def list_for_owner(
        self, owner_user_id: UUID, *, skip: int, limit: int
    ) -> list[FileDocument]:
        raise NotImplementedError

    async def get(self, file_id: UUID) -> FileDocument | None:
        raise NotImplementedError

    async def create(self, doc: FileDocument) -> FileDocument:
        raise NotImplementedError

    async def delete(self, file_id: UUID) -> bool:
        raise NotImplementedError


__all__ = ["FilesRepository"]
