"""Mongo repositories for DMC agents, portfolio, conversations and audit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.dmc.model import (
    AuditEventDocument,
    DmcAgentDocument,
    DmcConversationDocument,
    DmcConversationMessageDocument,
    DmcNotificationBatchDocument,
    DmcPortfolioLinkDocument,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class DmcAgentsRepository:
    COLLECTION: str = DmcAgentDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("user_id", ASCENDING)], unique=True, name="uniq_dmc_agent_user"
        )
        await self._collection.create_index(
            [("queue_position", ASCENDING), ("created_at", ASCENDING)],
            name="ix_dmc_queue",
        )

    async def get_by_user_id(self, user_id: UUID) -> DmcAgentDocument | None:
        raw = await self._collection.find_one({"user_id": user_id})
        return DmcAgentDocument.model_validate(raw) if raw else None

    async def create(self, doc: DmcAgentDocument) -> DmcAgentDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def update(
        self, user_id: UUID, fields: dict[str, Any]
    ) -> DmcAgentDocument | None:
        fields = {**fields, "updated_at": utcnow()}
        raw = await self._collection.find_one_and_update(
            {"user_id": user_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return DmcAgentDocument.model_validate(raw) if raw else None

    async def list_ordered(self) -> list[DmcAgentDocument]:
        cursor = self._collection.find({}).sort(
            [("queue_position", ASCENDING), ("created_at", ASCENDING)]
        )
        docs = await cursor.to_list(length=None)
        return [DmcAgentDocument.model_validate(doc) for doc in docs]

    async def max_queue_position(self) -> int:
        cursor = self._collection.find({}).sort("queue_position", DESCENDING).limit(1)
        docs = await cursor.to_list(length=1)
        if not docs:
            return -1
        return int(docs[0].get("queue_position", 0))

    async def next_queue_position(self) -> int:
        return await self.max_queue_position() + 1


class DmcPortfolioRepository:
    COLLECTION: str = DmcPortfolioLinkDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("agent_user_id", ASCENDING), ("company_id", ASCENDING)],
            unique=True,
            name="uniq_dmc_agent_company",
        )
        await self._collection.create_index(
            [("company_id", ASCENDING)], name="ix_dmc_portfolio_company"
        )

    async def list_for_agent(self, agent_user_id: UUID) -> list[DmcPortfolioLinkDocument]:
        cursor = self._collection.find({"agent_user_id": agent_user_id}).sort(
            "created_at", DESCENDING
        )
        docs = await cursor.to_list(length=None)
        return [DmcPortfolioLinkDocument.model_validate(doc) for doc in docs]

    async def get_link(
        self, agent_user_id: UUID, company_id: UUID
    ) -> DmcPortfolioLinkDocument | None:
        raw = await self._collection.find_one(
            {"agent_user_id": agent_user_id, "company_id": company_id}
        )
        return DmcPortfolioLinkDocument.model_validate(raw) if raw else None

    async def create(self, doc: DmcPortfolioLinkDocument) -> DmcPortfolioLinkDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def delete(self, agent_user_id: UUID, company_id: UUID) -> bool:
        result = await self._collection.delete_one(
            {"agent_user_id": agent_user_id, "company_id": company_id}
        )
        return result.deleted_count > 0


class DmcConversationsRepository:
    COLLECTION: str = DmcConversationDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("agent_user_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True,
            name="uniq_dmc_agent_user_conversation",
        )
        await self._collection.create_index(
            [("user_id", ASCENDING), ("last_message_at", DESCENDING)],
            name="ix_dmc_conversation_user",
        )

    async def get(self, conversation_id: UUID) -> DmcConversationDocument | None:
        raw = await self._collection.find_one({"_id": conversation_id})
        return DmcConversationDocument.model_validate(raw) if raw else None

    async def get_pair(
        self, agent_user_id: UUID, user_id: UUID
    ) -> DmcConversationDocument | None:
        raw = await self._collection.find_one(
            {"agent_user_id": agent_user_id, "user_id": user_id}
        )
        return DmcConversationDocument.model_validate(raw) if raw else None

    async def create(self, doc: DmcConversationDocument) -> DmcConversationDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def update(
        self, conversation_id: UUID, fields: dict[str, Any]
    ) -> DmcConversationDocument | None:
        fields = {**fields, "updated_at": utcnow()}
        raw = await self._collection.find_one_and_update(
            {"_id": conversation_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return DmcConversationDocument.model_validate(raw) if raw else None

    async def list_for_agent(self, agent_user_id: UUID) -> list[DmcConversationDocument]:
        cursor = self._collection.find({"agent_user_id": agent_user_id}).sort(
            "last_message_at", DESCENDING
        )
        docs = await cursor.to_list(length=None)
        return [DmcConversationDocument.model_validate(doc) for doc in docs]

    async def list_for_user(self, user_id: UUID) -> list[DmcConversationDocument]:
        cursor = self._collection.find({"user_id": user_id}).sort(
            "last_message_at", DESCENDING
        )
        docs = await cursor.to_list(length=None)
        return [DmcConversationDocument.model_validate(doc) for doc in docs]

    async def count_pending_for_agent(self, agent_user_id: UUID) -> int:
        return await self._collection.count_documents(
            {
                "agent_user_id": agent_user_id,
                "last_author_role": "user",
            }
        )


class DmcConversationMessagesRepository:
    COLLECTION: str = DmcConversationMessageDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("conversation_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_dmc_message_conversation",
        )

    async def create(
        self, doc: DmcConversationMessageDocument
    ) -> DmcConversationMessageDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def list_for_conversation(
        self, conversation_id: UUID
    ) -> list[DmcConversationMessageDocument]:
        cursor = self._collection.find({"conversation_id": conversation_id}).sort(
            "created_at", ASCENDING
        )
        docs = await cursor.to_list(length=None)
        return [DmcConversationMessageDocument.model_validate(doc) for doc in docs]


class DmcNotificationBatchesRepository:
    COLLECTION: str = DmcNotificationBatchDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("agent_user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_dmc_notification_agent",
        )

    async def create(
        self, doc: DmcNotificationBatchDocument
    ) -> DmcNotificationBatchDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def list_for_agent(
        self, agent_user_id: UUID, *, limit: int = 50
    ) -> list[DmcNotificationBatchDocument]:
        cursor = (
            self._collection.find({"agent_user_id": agent_user_id})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [DmcNotificationBatchDocument.model_validate(doc) for doc in docs]


class AuditEventsRepository:
    COLLECTION: str = AuditEventDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("created_at", DESCENDING)], name="ix_audit_created_at"
        )
        await self._collection.create_index(
            [("action", ASCENDING), ("created_at", DESCENDING)],
            name="ix_audit_action",
        )
        await self._collection.create_index(
            [("resource_type", ASCENDING), ("resource_id", ASCENDING)],
            name="ix_audit_resource",
        )

    async def create(self, doc: AuditEventDocument) -> AuditEventDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def list_recent(
        self, *, action_prefix: str = "dmc_", limit: int = 100
    ) -> list[AuditEventDocument]:
        cursor = (
            self._collection.find({"action": {"$regex": f"^{action_prefix}"}})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [AuditEventDocument.model_validate(doc) for doc in docs]


__all__ = [
    "AuditEventsRepository",
    "DmcAgentsRepository",
    "DmcConversationMessagesRepository",
    "DmcConversationsRepository",
    "DmcNotificationBatchesRepository",
    "DmcPortfolioRepository",
]
