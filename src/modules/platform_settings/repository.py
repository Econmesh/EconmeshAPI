"""Mongo repository for the platform settings singleton."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.modules.platform_settings.model import (
    PLATFORM_SETTINGS_ID,
    PlatformSettingsDocument,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class PlatformSettingsRepository:
    COLLECTION: str = PlatformSettingsDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        return None

    async def get_or_create(self) -> PlatformSettingsDocument:
        doc = await self._collection.find_one({"_id": PLATFORM_SETTINGS_ID})
        if doc:
            return PlatformSettingsDocument.model_validate(doc)
        settings = PlatformSettingsDocument()
        try:
            await self._collection.insert_one(settings.to_mongo())
        except DuplicateKeyError:
            existing = await self._collection.find_one({"_id": PLATFORM_SETTINGS_ID})
            if existing:
                return PlatformSettingsDocument.model_validate(existing)
            raise
        return settings

    async def update(self, patch: dict[str, Any]) -> PlatformSettingsDocument:
        await self.get_or_create()
        patch = {**patch, "updated_at": utcnow()}
        doc = await self._collection.find_one_and_update(
            {"_id": PLATFORM_SETTINGS_ID},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return await self.get_or_create()
        return PlatformSettingsDocument.model_validate(doc)


__all__ = ["PLATFORM_SETTINGS_ID", "PlatformSettingsRepository"]
