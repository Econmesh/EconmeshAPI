"""Data access for ``opportunities``."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.opportunities.model import OpportunityDocument, OpportunitySort
from src.modules.opportunities.schema import OpportunityListParams
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase

_SEARCH_FIELDS = (
    "title",
    "description",
    "category",
    "technical_detail",
    "company_name",
    "city",
)


class OpportunitiesRepository:
    COLLECTION: str = OpportunityDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("is_active", ASCENDING), ("created_at", DESCENDING)],
            name="ix_active_created_at",
        )
        await self._collection.create_index(
            [("company_id", ASCENDING)], name="ix_company_id"
        )
        await self._collection.create_index(
            [("owner_user_id", ASCENDING)], name="ix_owner_user_id"
        )
        await self._collection.create_index(
            [("opportunity_type", ASCENDING)], name="ix_opportunity_type"
        )
        await self._collection.create_index(
            [("offer_demand", ASCENDING)], name="ix_offer_demand"
        )
        await self._collection.create_index(
            [("category", ASCENDING)], name="ix_category"
        )
        await self._collection.create_index(
            [("state", ASCENDING)], name="ix_state"
        )
        await self._collection.create_index(
            [("periodicity", ASCENDING)], name="ix_periodicity"
        )
        await self._collection.create_index(
            [("price_negotiable", ASCENDING), ("price", ASCENDING)],
            name="ix_price_sort",
        )

    @staticmethod
    def _build_filter(params: OpportunityListParams) -> dict[str, Any]:
        query: dict[str, Any] = {"is_active": True}

        if params.q:
            escaped = re.escape(params.q.strip())
            query["$or"] = [
                {field: {"$regex": escaped, "$options": "i"}}
                for field in _SEARCH_FIELDS
            ]

        if params.opportunity_type is not None:
            query["opportunity_type"] = params.opportunity_type

        if params.offer_demand is not None:
            query["offer_demand"] = params.offer_demand

        if params.category is not None:
            query["category"] = params.category

        if params.state is not None:
            query["state"] = params.state

        if params.city is not None:
            escaped_city = re.escape(params.city.strip())
            query["city"] = {"$regex": f"^{escaped_city}$", "$options": "i"}

        if params.periodicity is not None:
            query["periodicity"] = params.periodicity

        if params.price_min is not None or params.price_max is not None:
            query["price_negotiable"] = False
            price_filter: dict[str, Any] = {"$ne": None}
            if params.price_min is not None:
                price_filter["$gte"] = params.price_min
            if params.price_max is not None:
                price_filter["$lte"] = params.price_max
            query["price"] = price_filter

        if params.quantity_min is not None or params.quantity_max is not None:
            quantity_filter: dict[str, Any] = {}
            if params.quantity_min is not None:
                quantity_filter["$gte"] = params.quantity_min
            if params.quantity_max is not None:
                quantity_filter["$lte"] = params.quantity_max
            query["quantity"] = quantity_filter

        return query

    @staticmethod
    def _build_sort(sort: OpportunitySort) -> list[tuple[str, int]]:
        match sort:
            case OpportunitySort.OLDEST:
                return [("created_at", ASCENDING)]
            case OpportunitySort.PRICE_ASC:
                return [("price_negotiable", ASCENDING), ("price", ASCENDING)]
            case OpportunitySort.PRICE_DESC:
                return [("price_negotiable", ASCENDING), ("price", DESCENDING)]
            case OpportunitySort.QUANTITY_DESC:
                return [("quantity", DESCENDING)]
            case _:
                return [("created_at", DESCENDING)]

    async def list_filtered(
        self, params: OpportunityListParams
    ) -> list[OpportunityDocument]:
        query = self._build_filter(params)
        sort = self._build_sort(params.sort)
        cursor = (
            self._collection.find(query)
            .sort(sort)
            .skip(params.skip)
            .limit(params.page_size)
        )
        docs = await cursor.to_list(length=params.page_size)
        return [OpportunityDocument.model_validate(doc) for doc in docs]

    async def count_filtered(self, params: OpportunityListParams) -> int:
        query = self._build_filter(params)
        return await self._collection.count_documents(query)

    async def get(self, opportunity_id: UUID) -> OpportunityDocument | None:
        doc = await self._collection.find_one({"_id": opportunity_id})
        return OpportunityDocument.model_validate(doc) if doc else None

    async def create(self, doc: OpportunityDocument) -> OpportunityDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def update(
        self, opportunity_id: UUID, patch: dict[str, object]
    ) -> OpportunityDocument | None:
        patch["updated_at"] = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": opportunity_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return OpportunityDocument.model_validate(doc) if doc else None

    async def delete(self, opportunity_id: UUID) -> bool:
        result = await self._collection.update_one(
            {"_id": opportunity_id},
            {"$set": {"is_active": False, "updated_at": utcnow()}},
        )
        return result.modified_count > 0


__all__ = ["OpportunitiesRepository"]
