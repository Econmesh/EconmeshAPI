"""Mongo aggregations for dashboard KPIs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.modules.agreements.model import AgreementDocument, AgreementStatus
from src.modules.auth.model import UserDocument
from src.modules.companies.model import CompanyDocument
from src.modules.contract_proposals.model import (
    ContractProposalDocument,
    ContractProposalStatus,
)
from src.modules.conversations.model import (
    ConversationStatus,
    OpportunityConversationDocument,
)
from src.modules.dashboard.labels import PENDING_AGREEMENT_STATUSES
from src.modules.opportunities.model import OpportunityDocument
from src.modules.support.model import SupportTicketDocument, SupportTicketStatus

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


def _group_count_pipeline(
    match: dict[str, Any],
    field: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    pipeline: list[dict[str, Any]] = [
        {"$match": match},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    if limit is not None:
        pipeline.append({"$limit": limit})
    return pipeline


def _daily_count_pipeline(
    match: dict[str, Any],
    *,
    since: datetime,
) -> list[dict[str, Any]]:
    return [
        {"$match": {**match, "created_at": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at",
                        "timezone": "UTC",
                    }
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]


class DashboardRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._users: AsyncCollection = db[UserDocument.collection_name]
        self._companies: AsyncCollection = db[CompanyDocument.collection_name]
        self._opportunities: AsyncCollection = db[OpportunityDocument.collection_name]
        self._conversations: AsyncCollection = db[
            OpportunityConversationDocument.collection_name
        ]
        self._proposals: AsyncCollection = db[ContractProposalDocument.collection_name]
        self._agreements: AsyncCollection = db[AgreementDocument.collection_name]
        self._support: AsyncCollection = db[SupportTicketDocument.collection_name]

    async def _count(self, collection: AsyncCollection, query: dict[str, Any]) -> int:
        return await collection.count_documents(query)

    async def _group_counts(
        self,
        collection: AsyncCollection,
        match: dict[str, Any],
        field: str,
        *,
        limit: int | None = None,
    ) -> list[tuple[str, int]]:
        cursor = await collection.aggregate(
            _group_count_pipeline(match, field, limit=limit)
        )
        rows = await cursor.to_list(length=limit or 200)
        result: list[tuple[str, int]] = []
        for row in rows:
            key = row.get("_id")
            if key is None:
                continue
            result.append((str(key), int(row.get("count", 0))))
        return result

    async def _daily_counts(
        self,
        collection: AsyncCollection,
        match: dict[str, Any],
        *,
        since: datetime,
    ) -> dict[str, int]:
        cursor = await collection.aggregate(
            _daily_count_pipeline(match, since=since)
        )
        rows = await cursor.to_list(length=400)
        return {str(row["_id"]): int(row.get("count", 0)) for row in rows if row.get("_id")}

    async def count_users(self, match: dict[str, Any] | None = None) -> int:
        return await self._count(self._users, match or {})

    async def count_companies(self, match: dict[str, Any]) -> int:
        return await self._count(self._companies, match)

    async def count_opportunities(self, match: dict[str, Any]) -> int:
        return await self._count(self._opportunities, match)

    async def count_conversations(self, match: dict[str, Any]) -> int:
        return await self._count(self._conversations, match)

    async def count_proposals(self, match: dict[str, Any]) -> int:
        return await self._count(self._proposals, match)

    async def count_agreements(self, match: dict[str, Any]) -> int:
        return await self._count(self._agreements, match)

    async def count_support(self, match: dict[str, Any]) -> int:
        return await self._count(self._support, match)

    async def group_opportunities_by(
        self, match: dict[str, Any], field: str, *, limit: int | None = None
    ) -> list[tuple[str, int]]:
        return await self._group_counts(self._opportunities, match, field, limit=limit)

    async def group_proposals_by(
        self, match: dict[str, Any], field: str
    ) -> list[tuple[str, int]]:
        return await self._group_counts(self._proposals, match, field)

    async def group_agreements_by(
        self, match: dict[str, Any], field: str
    ) -> list[tuple[str, int]]:
        return await self._group_counts(self._agreements, match, field)

    async def group_support_by(
        self, match: dict[str, Any], field: str
    ) -> list[tuple[str, int]]:
        return await self._group_counts(self._support, match, field)

    async def opportunity_gmv(self, match: dict[str, Any]) -> tuple[float, int, int]:
        """Return (estimated_gmv, with_price_count, negotiable_count)."""
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": None,
                    "gmv": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$ne": ["$price", None]},
                                        {"$eq": ["$price_negotiable", False]},
                                    ]
                                },
                                {"$multiply": ["$price", "$quantity"]},
                                0,
                            ]
                        }
                    },
                    "with_price": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$ne": ["$price", None]},
                                        {"$eq": ["$price_negotiable", False]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "negotiable": {
                        "$sum": {
                            "$cond": [{"$eq": ["$price_negotiable", True]}, 1, 0]
                        }
                    },
                }
            },
        ]
        cursor = await self._opportunities.aggregate(pipeline)
        rows = await cursor.to_list(length=1)
        if not rows:
            return 0.0, 0, 0
        row = rows[0]
        return float(row.get("gmv") or 0), int(row.get("with_price") or 0), int(
            row.get("negotiable") or 0
        )

    async def daily_series(
        self,
        *,
        days: int,
        opportunity_match: dict[str, Any],
        conversation_match: dict[str, Any],
        proposal_match: dict[str, Any],
        agreement_match: dict[str, Any],
    ) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=days - 1)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)

        opp = await self._daily_counts(
            self._opportunities, opportunity_match, since=since
        )
        conv = await self._daily_counts(
            self._conversations, conversation_match, since=since
        )
        prop = await self._daily_counts(self._proposals, proposal_match, since=since)
        signed_match = {
            **agreement_match,
            "status": AgreementStatus.SIGNED.value,
        }
        signed = await self._daily_counts(self._agreements, signed_match, since=since)

        points: list[dict[str, Any]] = []
        for offset in range(days):
            day = since + timedelta(days=offset)
            key = day.strftime("%Y-%m-%d")
            points.append(
                {
                    "date": key,
                    "opportunities": opp.get(key, 0),
                    "conversations": conv.get(key, 0),
                    "proposals": prop.get(key, 0),
                    "agreements_signed": signed.get(key, 0),
                }
            )
        return points

    async def list_company_ids_for_owner(self, owner_user_id: UUID) -> list[UUID]:
        cursor = self._companies.find(
            {"owner_user_id": owner_user_id, "is_active": True},
            {"_id": 1},
        )
        docs = await cursor.to_list(length=500)
        return [doc["_id"] for doc in docs]

    async def list_pending_proposals_for_user(
        self, user_id: UUID, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        cursor = (
            self._proposals.find(
                {
                    "is_active": True,
                    "status": ContractProposalStatus.PENDING_APPROVAL.value,
                    "$or": [
                        {"offerer_user_id": user_id},
                        {"interested_user_id": user_id},
                    ],
                },
                {"_id": 1, "title": 1, "updated_at": 1},
            )
            .sort("updated_at", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def list_pending_agreements_for_user(
        self, user_id: UUID, company_ids: list[UUID], *, limit: int = 5
    ) -> list[dict[str, Any]]:
        clauses: list[dict[str, Any]] = [
            {"owner_user_id": user_id},
            {"participants.user_id": user_id},
        ]
        if company_ids:
            clauses.append({"company_id": {"$in": company_ids}})
        cursor = (
            self._agreements.find(
                {
                    "is_active": True,
                    "status": {"$in": list(PENDING_AGREEMENT_STATUSES)},
                    "$or": clauses,
                },
                {"_id": 1, "title": 1, "status": 1, "updated_at": 1},
            )
            .sort("updated_at", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def list_open_conversations_for_user(
        self, user_id: UUID, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        cursor = (
            self._conversations.find(
                {
                    "is_active": True,
                    "status": ConversationStatus.OPEN.value,
                    "$or": [
                        {"offerer_user_id": user_id},
                        {"interested_user_id": user_id},
                    ],
                },
                {
                    "_id": 1,
                    "opportunity_title": 1,
                    "last_message_at": 1,
                    "updated_at": 1,
                },
            )
            .sort("last_message_at", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    @staticmethod
    def user_opportunity_match(user_id: UUID, company_ids: list[UUID]) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"owner_user_id": user_id}]
        if company_ids:
            clauses.append({"company_id": {"$in": company_ids}})
        return {"is_active": True, "$or": clauses}

    @staticmethod
    def user_conversation_match(user_id: UUID) -> dict[str, Any]:
        return {
            "is_active": True,
            "$or": [
                {"offerer_user_id": user_id},
                {"interested_user_id": user_id},
            ],
        }

    @staticmethod
    def user_proposal_match(user_id: UUID) -> dict[str, Any]:
        return {
            "is_active": True,
            "$or": [
                {"offerer_user_id": user_id},
                {"interested_user_id": user_id},
            ],
        }

    @staticmethod
    def user_agreement_match(user_id: UUID, company_ids: list[UUID]) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [
            {"owner_user_id": user_id},
            {"participants.user_id": user_id},
        ]
        if company_ids:
            clauses.append({"company_id": {"$in": company_ids}})
        return {"is_active": True, "$or": clauses}


__all__ = ["DashboardRepository"]
