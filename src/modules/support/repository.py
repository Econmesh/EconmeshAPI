"""Data access for support tickets and messages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.support.model import (
    SupportMessageDocument,
    SupportMessageType,
    SupportTicketDocument,
    SupportTicketSource,
    SupportTicketStatus,
)
from src.modules.support.schema import AdminSupportTicketListParams
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase

_USER_VISIBLE_TYPES = [
    SupportMessageType.USER_MESSAGE.value,
    SupportMessageType.ADMIN_REPLY.value,
]

_INTERNAL_SOURCE_QUERY: dict[str, Any] = {
    "$or": [
        {"source": SupportTicketSource.INTERNAL.value},
        {"source": {"$exists": False}},
    ]
}


class SupportTicketsRepository:
    COLLECTION: str = SupportTicketDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # Legacy unique index blocked all visitor tickets (user_id=null) from
        # sharing ticket_number values across external/contact_request sources.
        existing = await self._collection.index_information()
        if "uniq_user_ticket_number" in existing:
            await self._collection.drop_index("uniq_user_ticket_number")

        await self._collection.create_index(
            [("user_id", ASCENDING), ("ticket_number", ASCENDING)],
            unique=True,
            partialFilterExpression={"source": SupportTicketSource.INTERNAL.value},
            name="uniq_internal_user_ticket_number",
        )
        await self._collection.create_index(
            [("source", ASCENDING), ("ticket_number", ASCENDING)],
            unique=True,
            partialFilterExpression={"source": SupportTicketSource.EXTERNAL.value},
            name="uniq_external_ticket_number",
        )
        await self._collection.create_index(
            [("source", ASCENDING), ("ticket_number", ASCENDING)],
            unique=True,
            partialFilterExpression={
                "source": SupportTicketSource.CONTACT_REQUEST.value
            },
            name="uniq_contact_request_ticket_number",
        )
        await self._collection.create_index(
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="ix_user_status",
        )
        await self._collection.create_index(
            [("status", ASCENDING), ("last_message_at", DESCENDING)],
            name="ix_status_last_message",
        )
        await self._collection.create_index(
            [("assigned_admin_id", ASCENDING)], name="ix_assigned_admin"
        )
        await self._collection.create_index(
            [("last_message_at", DESCENDING)], name="ix_last_message_at"
        )
        await self._collection.create_index(
            [("source", ASCENDING), ("last_message_at", DESCENDING)],
            name="ix_source_last_message",
        )

    async def create(self, doc: SupportTicketDocument) -> SupportTicketDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get_by_id(self, ticket_id: UUID) -> SupportTicketDocument | None:
        raw = await self._collection.find_one({"_id": ticket_id})
        return SupportTicketDocument.model_validate(raw) if raw else None

    async def next_ticket_number(self, user_id: UUID) -> int:
        count = await self._collection.count_documents(
            {"user_id": user_id, **_INTERNAL_SOURCE_QUERY}
        )
        return count + 1

    async def next_external_ticket_number(self) -> int:
        count = await self._collection.count_documents(
            {"source": SupportTicketSource.EXTERNAL.value}
        )
        return count + 1

    async def next_contact_request_ticket_number(self) -> int:
        count = await self._collection.count_documents(
            {"source": SupportTicketSource.CONTACT_REQUEST.value}
        )
        return count + 1

    async def update(
        self, ticket_id: UUID, fields: dict[str, Any]
    ) -> SupportTicketDocument | None:
        fields = {**fields, "updated_at": utcnow()}
        raw = await self._collection.find_one_and_update(
            {"_id": ticket_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return SupportTicketDocument.model_validate(raw) if raw else None

    async def list_by_user(
        self,
        user_id: UUID,
        *,
        skip: int,
        limit: int,
        status: SupportTicketStatus | None = None,
    ) -> list[SupportTicketDocument]:
        query: dict[str, Any] = {"user_id": user_id, **_INTERNAL_SOURCE_QUERY}
        if status is not None:
            query["status"] = status
        cursor = (
            self._collection.find(query)
            .sort("last_message_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [SupportTicketDocument.model_validate(d) for d in docs]

    async def count_by_user(
        self, user_id: UUID, *, status: SupportTicketStatus | None = None
    ) -> int:
        query: dict[str, Any] = {"user_id": user_id, **_INTERNAL_SOURCE_QUERY}
        if status is not None:
            query["status"] = status
        return await self._collection.count_documents(query)

    async def list_admin(
        self, params: AdminSupportTicketListParams, *, skip: int
    ) -> list[SupportTicketDocument]:
        query = self._build_admin_filter(params)
        cursor = (
            self._collection.find(query)
            .sort("last_message_at", DESCENDING)
            .skip(skip)
            .limit(params.page_size)
        )
        docs = await cursor.to_list(length=params.page_size)
        return [SupportTicketDocument.model_validate(d) for d in docs]

    async def count_admin(self, params: AdminSupportTicketListParams) -> int:
        return await self._collection.count_documents(self._build_admin_filter(params))

    @staticmethod
    def _build_admin_filter(params: AdminSupportTicketListParams) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if params.status is not None:
            query["status"] = params.status
        if params.source is not None:
            if params.source == SupportTicketSource.INTERNAL:
                query.update(_INTERNAL_SOURCE_QUERY)
            else:
                query["source"] = params.source
        if params.q:
            escaped = re.escape(params.q.strip())
            if escaped.isdigit():
                query["ticket_number"] = int(escaped)
            else:
                query["subject"] = {"$regex": escaped, "$options": "i"}
        return query


class SupportMessagesRepository:
    COLLECTION: str = SupportMessageDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("ticket_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_ticket_created_at",
        )

    async def create(self, doc: SupportMessageDocument) -> SupportMessageDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def list_by_ticket(
        self,
        ticket_id: UUID,
        *,
        user_visible_only: bool = False,
    ) -> list[SupportMessageDocument]:
        query: dict[str, Any] = {"ticket_id": ticket_id}
        if user_visible_only:
            query["message_type"] = {"$in": _USER_VISIBLE_TYPES}
        cursor = self._collection.find(query).sort("created_at", ASCENDING)
        docs = await cursor.to_list(length=None)
        return [SupportMessageDocument.model_validate(d) for d in docs]

    async def mark_read(
        self,
        ticket_id: UUID,
        *,
        message_types: list[SupportMessageType],
        only_unread: bool = True,
    ) -> list[UUID]:
        query: dict[str, Any] = {
            "ticket_id": ticket_id,
            "message_type": {"$in": [t.value for t in message_types]},
        }
        if only_unread:
            query["read_at"] = None
        now = utcnow()
        cursor = self._collection.find(query, projection={"_id": 1})
        docs = await cursor.to_list(length=None)
        ids = [doc["_id"] for doc in docs]
        if not ids:
            return []
        await self._collection.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"read_at": now, "updated_at": now}},
        )
        return ids


__all__ = ["SupportMessagesRepository", "SupportTicketsRepository"]
