"""Data access for ``user_profiles``."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pymongo import ASCENDING, ReturnDocument

from src.modules.users.model import UserProfileDocument
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

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
        await self._collection.create_index(
            [("user_id", ASCENDING)], unique=True, name="uniq_user_id"
        )

    async def get_by_user(self, user_id: UUID) -> UserProfileDocument | None:
        doc = await self._collection.find_one({"user_id": user_id})
        return UserProfileDocument.model_validate(doc) if doc else None

    async def create(self, doc: UserProfileDocument) -> UserProfileDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def upsert_for_user(
        self, user_id: UUID, patch: dict[str, object]
    ) -> UserProfileDocument:
        now = utcnow()
        set_on_insert = {
            "_id": new_uuid(),
            "user_id": user_id,
            "created_at": now,
            "locale": "pt-BR",
            "preferences": {},
            "country": "BR",
        }
        patch["updated_at"] = now

        doc = await self._collection.find_one_and_update(
            {"user_id": user_id},
            {"$set": patch, "$setOnInsert": set_on_insert},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return UserProfileDocument.model_validate(doc)


__all__ = ["UsersRepository"]
