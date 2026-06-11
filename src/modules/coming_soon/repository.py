"""Data access for ``coming_soon_subscribers``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pymongo import ASCENDING

from src.modules.coming_soon.model import ComingSoonSubscriberDocument

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class ComingSoonRepository:
    COLLECTION: str = ComingSoonSubscriberDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("email", ASCENDING)],
            unique=True,
            name="uniq_email",
        )
        await self._collection.create_index(
            [("created_at", ASCENDING)],
            name="ix_created_at",
        )

    async def get_by_email(self, email: str) -> ComingSoonSubscriberDocument | None:
        doc = await self._collection.find_one({"email": email})
        return ComingSoonSubscriberDocument.model_validate(doc) if doc else None

    async def create(self, subscriber: ComingSoonSubscriberDocument) -> ComingSoonSubscriberDocument:
        await self._collection.insert_one(subscriber.to_mongo())
        return subscriber


__all__ = ["ComingSoonRepository"]
