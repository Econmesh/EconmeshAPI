"""Data access for opportunity conversations and messages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.conversations.model import (
    ConversationMessageType,
    ConversationStatus,
    OpportunityConversationDocument,
    OpportunityConversationMessageDocument,
)
from src.modules.conversations.schema import AdminConversationListParams
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase

_USER_VISIBLE_TYPES = [
    ConversationMessageType.PARTICIPANT_MESSAGE.value,
    ConversationMessageType.SYSTEM_EVENT.value,
]


class ConversationsRepository:
    COLLECTION: str = OpportunityConversationDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # Backfill so partial unique index covers legacy documents.
        await self._collection.update_many(
            {"is_active": {"$exists": False}},
            {"$set": {"is_active": True}},
        )
        # Drop legacy unique index (all rows) if present so partial unique works.
        try:
            await self._collection.drop_index("uniq_opportunity_interested_company")
        except Exception:  # noqa: BLE001
            pass
        await self._collection.create_index(
            [("opportunity_id", ASCENDING), ("interested_company_id", ASCENDING)],
            unique=True,
            name="uniq_opportunity_interested_company_active",
            partialFilterExpression={"is_active": True},
        )
        await self._collection.create_index(
            [("offerer_user_id", ASCENDING), ("last_message_at", DESCENDING)],
            name="ix_offerer_user_last_message",
        )
        await self._collection.create_index(
            [("interested_user_id", ASCENDING), ("last_message_at", DESCENDING)],
            name="ix_interested_user_last_message",
        )
        await self._collection.create_index(
            [("status", ASCENDING), ("last_message_at", DESCENDING)],
            name="ix_status_last_message",
        )
        await self._collection.create_index(
            [("last_message_at", DESCENDING)], name="ix_last_message_at"
        )

    async def create(
        self, doc: OpportunityConversationDocument
    ) -> OpportunityConversationDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get_by_id(
        self, conversation_id: UUID
    ) -> OpportunityConversationDocument | None:
        raw = await self._collection.find_one({"_id": conversation_id})
        return OpportunityConversationDocument.model_validate(raw) if raw else None

    async def get_by_opportunity_and_company(
        self, opportunity_id: UUID, interested_company_id: UUID
    ) -> OpportunityConversationDocument | None:
        raw = await self._collection.find_one(
            {
                "opportunity_id": opportunity_id,
                "interested_company_id": interested_company_id,
                "is_active": True,
            }
        )
        return OpportunityConversationDocument.model_validate(raw) if raw else None

    async def update(
        self, conversation_id: UUID, fields: dict[str, Any]
    ) -> OpportunityConversationDocument | None:
        fields = {**fields, "updated_at": utcnow()}
        raw = await self._collection.find_one_and_update(
            {"_id": conversation_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return OpportunityConversationDocument.model_validate(raw) if raw else None

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        skip: int,
        limit: int,
        status: ConversationStatus | None = None,
    ) -> list[OpportunityConversationDocument]:
        query: dict[str, Any] = {
            "$or": [
                {"offerer_user_id": user_id},
                {"interested_user_id": user_id},
            ]
        }
        if status is not None:
            query["status"] = status
        cursor = (
            self._collection.find(query)
            .sort("last_message_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [OpportunityConversationDocument.model_validate(d) for d in docs]

    async def count_for_user(
        self, user_id: UUID, *, status: ConversationStatus | None = None
    ) -> int:
        query: dict[str, Any] = {
            "$or": [
                {"offerer_user_id": user_id},
                {"interested_user_id": user_id},
            ]
        }
        if status is not None:
            query["status"] = status
        return await self._collection.count_documents(query)

    async def list_admin(
        self, params: AdminConversationListParams, *, skip: int
    ) -> list[OpportunityConversationDocument]:
        query = self._build_admin_filter(params)
        cursor = (
            self._collection.find(query)
            .sort("last_message_at", DESCENDING)
            .skip(skip)
            .limit(params.page_size)
        )
        docs = await cursor.to_list(length=params.page_size)
        return [OpportunityConversationDocument.model_validate(d) for d in docs]

    async def count_admin(self, params: AdminConversationListParams) -> int:
        return await self._collection.count_documents(self._build_admin_filter(params))

    @staticmethod
    def _build_admin_filter(params: AdminConversationListParams) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if params.status is not None:
            query["status"] = params.status
        if params.q:
            escaped = re.escape(params.q.strip())
            query["$or"] = [
                {"opportunity_title": {"$regex": escaped, "$options": "i"}},
                {"offerer_company_name": {"$regex": escaped, "$options": "i"}},
                {"interested_company_name": {"$regex": escaped, "$options": "i"}},
            ]
        return query


class ConversationMessagesRepository:
    COLLECTION: str = OpportunityConversationMessageDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("conversation_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_conversation_created_at",
        )

    async def create(
        self, doc: OpportunityConversationMessageDocument
    ) -> OpportunityConversationMessageDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def list_by_conversation(
        self,
        conversation_id: UUID,
        *,
        user_visible_only: bool = False,
    ) -> list[OpportunityConversationMessageDocument]:
        query: dict[str, Any] = {"conversation_id": conversation_id}
        if user_visible_only:
            query["message_type"] = {"$in": _USER_VISIBLE_TYPES}
        cursor = self._collection.find(query).sort("created_at", ASCENDING)
        docs = await cursor.to_list(length=None)
        return [OpportunityConversationMessageDocument.model_validate(d) for d in docs]

    async def mark_read(
        self,
        conversation_id: UUID,
        *,
        exclude_author_id: UUID,
        message_types: list[ConversationMessageType],
        only_unread: bool = True,
    ) -> list[UUID]:
        query: dict[str, Any] = {
            "conversation_id": conversation_id,
            "author_id": {"$ne": exclude_author_id},
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


__all__ = ["ConversationMessagesRepository", "ConversationsRepository"]
