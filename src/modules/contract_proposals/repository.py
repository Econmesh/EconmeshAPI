"""Data access for contract proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.modules.contract_proposals.model import (
    ContractProposalDocument,
    ContractProposalStatus,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


_ACTIVE_STATUSES = [
    ContractProposalStatus.DRAFT,
    ContractProposalStatus.PENDING_APPROVAL,
    ContractProposalStatus.CHANGES_REQUESTED,
    ContractProposalStatus.APPROVED,
    ContractProposalStatus.SENT_TO_AGREEMENTS,
]

_NEGOTIATING_STATUSES = [
    ContractProposalStatus.DRAFT,
    ContractProposalStatus.PENDING_APPROVAL,
    ContractProposalStatus.CHANGES_REQUESTED,
]


class ContractProposalsRepository:
    COLLECTION: str = ContractProposalDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("conversation_id", ASCENDING), ("status", ASCENDING)],
            name="ix_conversation_status",
        )
        await self._collection.create_index(
            [("offerer_user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_offerer_created",
        )
        await self._collection.create_index(
            [("interested_user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_interested_created",
        )
        await self._collection.create_index(
            [("opportunity_id", ASCENDING)], name="ix_opportunity"
        )

    async def create(self, doc: ContractProposalDocument) -> ContractProposalDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get(self, proposal_id: UUID) -> ContractProposalDocument | None:
        raw = await self._collection.find_one({"_id": proposal_id, "is_active": True})
        return ContractProposalDocument.model_validate(raw) if raw else None

    async def replace(self, doc: ContractProposalDocument) -> ContractProposalDocument:
        doc.updated_at = utcnow()
        await self._collection.replace_one({"_id": doc.id}, doc.to_mongo())
        return doc

    async def find_active_for_conversation(
        self, conversation_id: UUID
    ) -> ContractProposalDocument | None:
        raw = await self._collection.find_one(
            {
                "conversation_id": conversation_id,
                "is_active": True,
                "status": {"$in": _ACTIVE_STATUSES},
            }
        )
        return ContractProposalDocument.model_validate(raw) if raw else None

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
        skip: int,
        limit: int,
    ) -> list[ContractProposalDocument]:
        query: dict[str, Any] = {
            "is_active": True,
            "$or": [
                {"offerer_user_id": user_id},
                {"interested_user_id": user_id},
            ],
        }
        if conversation_id is not None:
            query["conversation_id"] = conversation_id
        cursor = (
            self._collection.find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [ContractProposalDocument.model_validate(doc) for doc in docs]

    async def count_for_user(
        self, *, user_id: UUID, conversation_id: UUID | None
    ) -> int:
        query: dict[str, Any] = {
            "is_active": True,
            "$or": [
                {"offerer_user_id": user_id},
                {"interested_user_id": user_id},
            ],
        }
        if conversation_id is not None:
            query["conversation_id"] = conversation_id
        return await self._collection.count_documents(query)

    async def list_all(
        self,
        *,
        conversation_id: UUID | None,
        skip: int,
        limit: int,
    ) -> list[ContractProposalDocument]:
        query: dict[str, Any] = {"is_active": True}
        if conversation_id is not None:
            query["conversation_id"] = conversation_id
        cursor = (
            self._collection.find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [ContractProposalDocument.model_validate(doc) for doc in docs]

    async def count_all(self, *, conversation_id: UUID | None) -> int:
        query: dict[str, Any] = {"is_active": True}
        if conversation_id is not None:
            query["conversation_id"] = conversation_id
        return await self._collection.count_documents(query)

    async def list_negotiating(
        self,
        *,
        contract_types: list[Any] | None = None,
    ) -> list[ContractProposalDocument]:
        """List active minutas still in negotiation (not approved/rejected/sent)."""
        query: dict[str, Any] = {
            "is_active": True,
            "status": {"$in": _NEGOTIATING_STATUSES},
        }
        if contract_types is not None:
            query["contract_type"] = {
                "$in": [t.value if hasattr(t, "value") else t for t in contract_types]
            }
        cursor = self._collection.find(query).sort("updated_at", DESCENDING)
        docs = await cursor.to_list(length=10_000)
        return [ContractProposalDocument.model_validate(doc) for doc in docs]


__all__ = ["ContractProposalsRepository"]
