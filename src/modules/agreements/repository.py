"""Data access for ``agreements`` and ``agreement_events``."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.agreements.model import (
    AgreementDocument,
    AgreementEventDocument,
    AgreementFilter,
    AgreementSort,
    AgreementStatus,
)
from src.modules.agreements.schema import AgreementListParams
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase

_SEARCH_FIELDS = ("title", "description", "company_name", "verification_code")


class AgreementsRepository:
    COLLECTION: str = AgreementDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("is_active", ASCENDING), ("created_at", DESCENDING)],
            name="ix_active_created_at",
        )
        await self._collection.create_index(
            [("owner_user_id", ASCENDING)], name="ix_owner_user_id"
        )
        await self._collection.create_index(
            [("company_id", ASCENDING)], name="ix_company_id"
        )
        await self._collection.create_index(
            [("status", ASCENDING)], name="ix_status"
        )
        await self._collection.create_index(
            [("verification_code", ASCENDING)],
            unique=True,
            name="uniq_verification_code",
        )
        await self._collection.create_index(
            [("participants.email", ASCENDING)], name="ix_participant_email"
        )
        await self._collection.create_index(
            [("participants.user_id", ASCENDING)], name="ix_participant_user_id"
        )
        await self._collection.create_index(
            [("deadline", ASCENDING)], name="ix_deadline"
        )

    @staticmethod
    def _visibility_clause(*, user_id: UUID, email: str | None) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [
            {"owner_user_id": user_id},
            {"participants.user_id": user_id},
        ]
        if email:
            clauses.append({"participants.email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})
        return {"$or": clauses}

    def _build_filter(
        self,
        params: AgreementListParams,
        *,
        user_id: UUID,
        email: str | None,
        is_admin: bool,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"is_active": True}

        if not is_admin:
            query.update(self._visibility_clause(user_id=user_id, email=email))

        if params.q:
            escaped = re.escape(params.q.strip())
            query["$and"] = query.get("$and", [])
            query["$and"].append(
                {
                    "$or": [
                        {field: {"$regex": escaped, "$options": "i"}}
                        for field in _SEARCH_FIELDS
                    ]
                }
            )

        if params.company_id is not None:
            query["company_id"] = params.company_id

        match params.filter:
            case AgreementFilter.SIGNED:
                query["status"] = AgreementStatus.SIGNED
            case AgreementFilter.PENDING:
                query["status"] = {
                    "$in": [
                        AgreementStatus.AWAITING_SIGNATURES,
                        AgreementStatus.PARTIALLY_SIGNED,
                        AgreementStatus.AWAITING_SEND,
                    ]
                }
            case AgreementFilter.MINE:
                query["owner_user_id"] = user_id
            case AgreementFilter.ORGANIZATION | AgreementFilter.COMPANY:
                if params.company_id is None:
                    # Restrict to agreements where user participates via any company they own
                    # is handled at service layer; keep visibility only.
                    pass
            case AgreementFilter.REJECTED:
                query["status"] = AgreementStatus.REJECTED
            case AgreementFilter.EXPIRED:
                query["status"] = AgreementStatus.EXPIRED
            case _:
                pass

        return query

    @staticmethod
    def _build_sort(sort: AgreementSort) -> list[tuple[str, int]]:
        match sort:
            case AgreementSort.OLDEST:
                return [("created_at", ASCENDING)]
            case AgreementSort.UPDATED:
                return [("updated_at", DESCENDING)]
            case AgreementSort.TITLE:
                return [("title", ASCENDING)]
            case _:
                return [("created_at", DESCENDING)]

    async def list_filtered(
        self,
        params: AgreementListParams,
        *,
        user_id: UUID,
        email: str | None,
        is_admin: bool = False,
    ) -> list[AgreementDocument]:
        query = self._build_filter(
            params, user_id=user_id, email=email, is_admin=is_admin
        )
        cursor = (
            self._collection.find(query)
            .sort(self._build_sort(params.sort))
            .skip(params.skip if hasattr(params, "skip") else (params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
        docs = await cursor.to_list(length=params.page_size)
        return [AgreementDocument.model_validate(doc) for doc in docs]

    async def count_filtered(
        self,
        params: AgreementListParams,
        *,
        user_id: UUID,
        email: str | None,
        is_admin: bool = False,
    ) -> int:
        query = self._build_filter(
            params, user_id=user_id, email=email, is_admin=is_admin
        )
        return await self._collection.count_documents(query)

    async def get(self, agreement_id: UUID) -> AgreementDocument | None:
        doc = await self._collection.find_one({"_id": agreement_id})
        return AgreementDocument.model_validate(doc) if doc else None

    async def create(self, doc: AgreementDocument) -> AgreementDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def replace(self, doc: AgreementDocument) -> AgreementDocument:
        doc.touch()
        await self._collection.replace_one({"_id": doc.id}, doc.to_mongo())
        return doc

    async def update(
        self, agreement_id: UUID, patch: dict[str, object]
    ) -> AgreementDocument | None:
        patch["updated_at"] = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": agreement_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return AgreementDocument.model_validate(doc) if doc else None

    async def list_expired_candidates(self, *, now: Any) -> list[AgreementDocument]:
        cursor = self._collection.find(
            {
                "is_active": True,
                "deadline": {"$lt": now},
                "status": {
                    "$in": [
                        AgreementStatus.AWAITING_SIGNATURES,
                        AgreementStatus.PARTIALLY_SIGNED,
                    ]
                },
            }
        )
        docs = await cursor.to_list(length=500)
        return [AgreementDocument.model_validate(doc) for doc in docs]


class AgreementEventsRepository:
    COLLECTION: str = AgreementEventDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("agreement_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_agreement_created_at",
        )

    async def create(self, doc: AgreementEventDocument) -> AgreementEventDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def list_for_agreement(
        self, agreement_id: UUID
    ) -> list[AgreementEventDocument]:
        cursor = self._collection.find({"agreement_id": agreement_id}).sort(
            "created_at", ASCENDING
        )
        docs = await cursor.to_list(length=2000)
        return [AgreementEventDocument.model_validate(doc) for doc in docs]


__all__ = ["AgreementEventsRepository", "AgreementsRepository"]
