"""Data access for ``companies``."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pymongo import ASCENDING, ReturnDocument

from src.modules.companies.model import CompanyDocument
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class CompaniesRepository:
    COLLECTION: str = CompanyDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("owner_user_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_owner_created_at",
        )
        await self._collection.create_index(
            [("country", ASCENDING), ("tax_id", ASCENDING)],
            unique=True,
            name="uniq_country_tax_id",
        )
        await self._collection.create_index(
            [("is_active", ASCENDING)], name="ix_is_active"
        )

    async def list_for_owner(
        self, owner_user_id: UUID, *, skip: int, limit: int
    ) -> list[CompanyDocument]:
        cursor = (
            self._collection.find({"owner_user_id": owner_user_id, "is_active": True})
            .sort("created_at", ASCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [CompanyDocument.model_validate(doc) for doc in docs]

    async def count_for_owner(self, owner_user_id: UUID) -> int:
        return await self._collection.count_documents(
            {"owner_user_id": owner_user_id, "is_active": True}
        )

    async def get(self, company_id: UUID) -> CompanyDocument | None:
        doc = await self._collection.find_one({"_id": company_id})
        return CompanyDocument.model_validate(doc) if doc else None

    async def get_by_tax_id(self, country: str, tax_id: str) -> CompanyDocument | None:
        doc = await self._collection.find_one({"country": country, "tax_id": tax_id})
        return CompanyDocument.model_validate(doc) if doc else None

    async def create(self, doc: CompanyDocument) -> CompanyDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def update(
        self, company_id: UUID, patch: dict[str, object]
    ) -> CompanyDocument | None:
        patch["updated_at"] = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": company_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return CompanyDocument.model_validate(doc) if doc else None

    async def delete(self, company_id: UUID) -> bool:
        result = await self._collection.update_one(
            {"_id": company_id},
            {"$set": {"is_active": False, "updated_at": utcnow()}},
        )
        return result.modified_count > 0


__all__ = ["CompaniesRepository"]
