"""Data access for contract section templates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.contract_sections.model import (
    ContractSectionTemplateDocument,
    ContractType,
    SectionAppliesTo,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class ContractSectionsRepository:
    COLLECTION: str = ContractSectionTemplateDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [
                ("contract_type", ASCENDING),
                ("is_active", ASCENDING),
                ("sort_order", ASCENDING),
            ],
            name="ix_type_active_sort",
        )
        await self._collection.create_index(
            [("created_at", DESCENDING)], name="ix_created_at"
        )

    async def create(
        self, doc: ContractSectionTemplateDocument
    ) -> ContractSectionTemplateDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get_by_id(
        self, section_id: UUID
    ) -> ContractSectionTemplateDocument | None:
        doc = await self._collection.find_one({"_id": section_id})
        return ContractSectionTemplateDocument.model_validate(doc) if doc else None

    async def list_sections(
        self,
        *,
        skip: int,
        limit: int,
        contract_type: SectionAppliesTo | None = None,
        active_only: bool = False,
    ) -> list[ContractSectionTemplateDocument]:
        query: dict[str, Any] = {}
        if active_only:
            query["is_active"] = True
        if contract_type is not None:
            query["contract_type"] = contract_type
        cursor = (
            self._collection.find(query)
            .sort([("sort_order", ASCENDING), ("created_at", DESCENDING)])
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [ContractSectionTemplateDocument.model_validate(doc) for doc in docs]

    async def count_sections(
        self,
        *,
        contract_type: SectionAppliesTo | None = None,
        active_only: bool = False,
    ) -> int:
        query: dict[str, Any] = {}
        if active_only:
            query["is_active"] = True
        if contract_type is not None:
            query["contract_type"] = contract_type
        return await self._collection.count_documents(query)

    async def list_active_by_type(
        self, contract_type: ContractType | str
    ) -> list[ContractSectionTemplateDocument]:
        """Active templates for a proposal type (specific + oportunidades + todos)."""
        type_value = (
            contract_type.value if hasattr(contract_type, "value") else str(contract_type)
        )
        cursor = self._collection.find(
            {
                "is_active": True,
                "contract_type": {
                    "$in": [
                        type_value,
                        SectionAppliesTo.OPORTUNIDADES.value,
                        SectionAppliesTo.TODOS.value,
                    ]
                },
            }
        ).sort([("sort_order", ASCENDING), ("created_at", ASCENDING)])
        docs = await cursor.to_list(length=500)
        return [ContractSectionTemplateDocument.model_validate(doc) for doc in docs]

    async def update(
        self, section_id: UUID, patch: dict[str, object]
    ) -> ContractSectionTemplateDocument | None:
        patch["updated_at"] = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": section_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return ContractSectionTemplateDocument.model_validate(doc) if doc else None

    async def soft_delete(self, section_id: UUID) -> bool:
        result = await self._collection.update_one(
            {"_id": section_id},
            {"$set": {"is_active": False, "updated_at": utcnow()}},
        )
        return result.modified_count > 0


__all__ = ["ContractSectionsRepository"]
