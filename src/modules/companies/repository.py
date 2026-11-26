"""Data access for ``companies``."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pymongo import ASCENDING, ReturnDocument

from src.modules.companies.model import CompanyDocument, CompanyRegistrationStatus
from src.shared.utils.time import utcnow

_COMPLETE_ACTIVE: dict = {
    "is_active": True,
    "$or": [
        {"registration_status": CompanyRegistrationStatus.COMPLETE.value},
        {"registration_status": {"$exists": False}},
    ],
}

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
        await self._collection.create_index(
            [("registration_status", ASCENDING), ("is_active", ASCENDING)],
            name="ix_registration_status_active",
        )
        indexes = await self._collection.index_information()
        if "uniq_active_owner_user_id" in indexes:
            await self._collection.drop_index("uniq_active_owner_user_id")
        await self._collection.create_index(
            [("owner_user_id", ASCENDING)],
            unique=True,
            name="uniq_active_owner_user_id",
            partialFilterExpression={
                "is_active": True,
                "owner_user_id": {"$exists": True, "$type": "binData"},
            },
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

    async def list_all(
        self, *, skip: int, limit: int, include_pre_registered: bool = True
    ) -> list[CompanyDocument]:
        query: dict = {"is_active": True} if include_pre_registered else dict(_COMPLETE_ACTIVE)
        cursor = (
            self._collection.find(query)
            .sort("created_at", ASCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [CompanyDocument.model_validate(doc) for doc in docs]

    async def count_all(self, *, include_pre_registered: bool = True) -> int:
        query: dict = {"is_active": True} if include_pre_registered else dict(_COMPLETE_ACTIVE)
        return await self._collection.count_documents(query)

    async def get(self, company_id: UUID) -> CompanyDocument | None:
        doc = await self._collection.find_one({"_id": company_id})
        return CompanyDocument.model_validate(doc) if doc else None

    async def get_by_tax_id(self, country: str, tax_id: str) -> CompanyDocument | None:
        doc = await self._collection.find_one({"country": country, "tax_id": tax_id})
        return CompanyDocument.model_validate(doc) if doc else None

    def _text_search_query(
        self, q: str, *, status: CompanyRegistrationStatus | None = None
    ) -> dict:
        import re

        escaped = re.escape(q.strip()) if q.strip() else ""
        filters: list[dict] = [{"is_active": True}]
        if status is CompanyRegistrationStatus.PRE_REGISTERED:
            filters.append(
                {"registration_status": CompanyRegistrationStatus.PRE_REGISTERED.value}
            )
        elif status is CompanyRegistrationStatus.COMPLETE:
            filters.append(
                {
                    "$or": [
                        {
                            "registration_status": CompanyRegistrationStatus.COMPLETE.value
                        },
                        {"registration_status": {"$exists": False}},
                    ]
                }
            )
        if escaped:
            digits = "".join(ch for ch in q if ch.isdigit())
            clauses: list[dict] = [
                {"legal_name": {"$regex": escaped, "$options": "i"}},
                {"trade_name": {"$regex": escaped, "$options": "i"}},
                {"tax_id": {"$regex": escaped, "$options": "i"}},
            ]
            if digits:
                clauses.append({"tax_id": {"$regex": re.escape(digits)}})
            filters.append({"$or": clauses})
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}

    async def search(
        self,
        q: str,
        *,
        limit: int = 20,
        include_pre_registered: bool = False,
    ) -> list[CompanyDocument]:
        status = None if include_pre_registered else CompanyRegistrationStatus.COMPLETE
        query = self._text_search_query(q, status=status)
        cursor = self._collection.find(query).sort("legal_name", ASCENDING).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [CompanyDocument.model_validate(doc) for doc in docs]

    async def search_pre_registrations(self, q: str, *, limit: int = 8) -> list[CompanyDocument]:
        query = self._text_search_query(q, status=CompanyRegistrationStatus.PRE_REGISTERED)
        cursor = self._collection.find(query).sort("legal_name", ASCENDING).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [CompanyDocument.model_validate(doc) for doc in docs]

    async def get_pre_registration(self, company_id: UUID) -> CompanyDocument | None:
        doc = await self._collection.find_one(
            {
                "_id": company_id,
                "is_active": True,
                "registration_status": CompanyRegistrationStatus.PRE_REGISTERED.value,
            }
        )
        return CompanyDocument.model_validate(doc) if doc else None

    async def claim_pre_registration(
        self, company_id: UUID, patch: dict[str, object]
    ) -> CompanyDocument | None:
        """Atomically turn a pre-registration into a complete, owned company.

        Returns ``None`` when the document is no longer a pre-registration
        (e.g. another user claimed it first).
        """
        patch = {
            **patch,
            "registration_status": CompanyRegistrationStatus.COMPLETE.value,
            "updated_at": utcnow(),
        }
        doc = await self._collection.find_one_and_update(
            {
                "_id": company_id,
                "is_active": True,
                "registration_status": CompanyRegistrationStatus.PRE_REGISTERED.value,
                "owner_user_id": None,
            },
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return CompanyDocument.model_validate(doc) if doc else None

    async def restore(self, original: CompanyDocument) -> None:
        """Put a document back exactly as it was (rollback of a failed claim)."""
        await self._collection.replace_one({"_id": original.id}, original.to_mongo())

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

    async def hard_delete(self, company_id: UUID) -> bool:
        result = await self._collection.delete_one({"_id": company_id})
        return result.deleted_count > 0

    async def list_active_except(
        self, exclude_ids: set[UUID], *, skip: int, limit: int
    ) -> list[CompanyDocument]:
        query: dict = dict(_COMPLETE_ACTIVE)
        if exclude_ids:
            query["_id"] = {"$nin": list(exclude_ids)}
        cursor = (
            self._collection.find(query)
            .sort("created_at", ASCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [CompanyDocument.model_validate(doc) for doc in docs]

    async def count_active_except(self, exclude_ids: set[UUID]) -> int:
        query: dict = dict(_COMPLETE_ACTIVE)
        if exclude_ids:
            query["_id"] = {"$nin": list(exclude_ids)}
        return await self._collection.count_documents(query)

    async def get_many(self, company_ids: list[UUID]) -> dict[UUID, CompanyDocument]:
        if not company_ids:
            return {}
        cursor = self._collection.find({"_id": {"$in": company_ids}})
        docs = await cursor.to_list(length=len(company_ids))
        companies = [CompanyDocument.model_validate(doc) for doc in docs]
        return {c.id: c for c in companies}


__all__ = ["CompaniesRepository"]
