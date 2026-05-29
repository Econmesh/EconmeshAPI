"""Data access for ``user_profiles``. SKELETON — fill the body when needed."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.modules.users.model import UserProfileDocument

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class UsersRepository:
    """Async repository for the ``user_profiles`` collection."""

    COLLECTION: str = UserProfileDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # TODO: create unique index on user_id
        raise NotImplementedError

    async def list(self, *, skip: int, limit: int) -> list[UserProfileDocument]:
        # TODO: paginated find
        raise NotImplementedError

    async def get(self, profile_id: UUID) -> UserProfileDocument | None:
        # TODO: find_one by _id
        raise NotImplementedError

    async def get_by_user(self, user_id: UUID) -> UserProfileDocument | None:
        # TODO: find_one by user_id
        raise NotImplementedError

    async def create(self, doc: UserProfileDocument) -> UserProfileDocument:
        # TODO: insert_one + return doc
        raise NotImplementedError

    async def update(
        self, profile_id: UUID, patch: dict[str, object]
    ) -> UserProfileDocument | None:
        # TODO: find_one_and_update with RETURN_AFTER
        raise NotImplementedError

    async def delete(self, profile_id: UUID) -> bool:
        # TODO: delete_one
        raise NotImplementedError


__all__ = ["UsersRepository"]
