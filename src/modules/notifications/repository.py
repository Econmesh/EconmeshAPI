"""Data access for notification collections."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.notifications.model import (
    NotificationCampaignDocument,
    NotificationCampaignStats,
    NotificationCampaignStatus,
    NotificationGroupDocument,
    UserNotificationDocument,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class NotificationGroupsRepository:
    COLLECTION: str = NotificationGroupDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("is_active", ASCENDING), ("created_at", DESCENDING)],
            name="ix_active_created_at",
        )
        await self._collection.create_index(
            [("created_by", ASCENDING)], name="ix_created_by"
        )

    async def create(self, doc: NotificationGroupDocument) -> NotificationGroupDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get_by_id(self, group_id: UUID) -> NotificationGroupDocument | None:
        doc = await self._collection.find_one({"_id": group_id})
        return NotificationGroupDocument.model_validate(doc) if doc else None

    async def list_groups(
        self, *, skip: int, limit: int, active_only: bool = True
    ) -> list[NotificationGroupDocument]:
        query: dict[str, Any] = {}
        if active_only:
            query["is_active"] = True
        cursor = (
            self._collection.find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [NotificationGroupDocument.model_validate(doc) for doc in docs]

    async def count_groups(self, *, active_only: bool = True) -> int:
        query: dict[str, Any] = {}
        if active_only:
            query["is_active"] = True
        return await self._collection.count_documents(query)

    async def get_by_ids(
        self, group_ids: list[UUID], *, active_only: bool = True
    ) -> list[NotificationGroupDocument]:
        if not group_ids:
            return []
        query: dict[str, Any] = {"_id": {"$in": group_ids}}
        if active_only:
            query["is_active"] = True
        cursor = self._collection.find(query)
        docs = await cursor.to_list(length=len(group_ids))
        return [NotificationGroupDocument.model_validate(doc) for doc in docs]

    async def update(
        self, group_id: UUID, patch: dict[str, object]
    ) -> NotificationGroupDocument | None:
        patch["updated_at"] = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": group_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return NotificationGroupDocument.model_validate(doc) if doc else None

    async def soft_delete(self, group_id: UUID) -> bool:
        result = await self._collection.update_one(
            {"_id": group_id},
            {"$set": {"is_active": False, "updated_at": utcnow()}},
        )
        return result.modified_count > 0


class NotificationCampaignsRepository:
    COLLECTION: str = NotificationCampaignDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("status", ASCENDING), ("send_at", ASCENDING)],
            name="ix_status_send_at",
        )
        await self._collection.create_index(
            [("created_at", DESCENDING)], name="ix_created_at"
        )
        await self._collection.create_index(
            [("created_by", ASCENDING)], name="ix_created_by"
        )

    async def create(
        self, doc: NotificationCampaignDocument
    ) -> NotificationCampaignDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get_by_id(
        self, campaign_id: UUID
    ) -> NotificationCampaignDocument | None:
        doc = await self._collection.find_one({"_id": campaign_id})
        return NotificationCampaignDocument.model_validate(doc) if doc else None

    async def list_campaigns(
        self, *, skip: int, limit: int
    ) -> list[NotificationCampaignDocument]:
        cursor = (
            self._collection.find({})
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [NotificationCampaignDocument.model_validate(doc) for doc in docs]

    async def count_campaigns(self) -> int:
        return await self._collection.count_documents({})

    async def update(
        self, campaign_id: UUID, patch: dict[str, object]
    ) -> NotificationCampaignDocument | None:
        patch["updated_at"] = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": campaign_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return NotificationCampaignDocument.model_validate(doc) if doc else None

    async def claim_for_processing(
        self, campaign_id: UUID
    ) -> NotificationCampaignDocument | None:
        doc = await self._collection.find_one_and_update(
            {
                "_id": campaign_id,
                "status": {
                    "$in": [
                        NotificationCampaignStatus.SCHEDULED.value,
                        NotificationCampaignStatus.DRAFT.value,
                    ]
                },
            },
            {
                "$set": {
                    "status": NotificationCampaignStatus.PROCESSING.value,
                    "updated_at": utcnow(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return NotificationCampaignDocument.model_validate(doc) if doc else None

    async def list_due_scheduled(
        self, *, now: datetime, limit: int = 50
    ) -> list[NotificationCampaignDocument]:
        cursor = (
            self._collection.find(
                {
                    "status": NotificationCampaignStatus.SCHEDULED.value,
                    "send_at": {"$lte": now},
                }
            )
            .sort("send_at", ASCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [NotificationCampaignDocument.model_validate(doc) for doc in docs]


class UserNotificationsRepository:
    COLLECTION: str = UserNotificationDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_user_created_at",
        )
        await self._collection.create_index(
            [("user_id", ASCENDING), ("read_at", ASCENDING)],
            name="ix_user_read_at",
        )
        await self._collection.create_index(
            [("campaign_id", ASCENDING)], name="ix_campaign_id"
        )

    async def create_many(
        self, docs: list[UserNotificationDocument]
    ) -> list[UserNotificationDocument]:
        if not docs:
            return []
        await self._collection.insert_many([doc.to_mongo() for doc in docs])
        return docs

    async def create(self, doc: UserNotificationDocument) -> UserNotificationDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get_by_id(
        self, notification_id: UUID
    ) -> UserNotificationDocument | None:
        doc = await self._collection.find_one({"_id": notification_id})
        return UserNotificationDocument.model_validate(doc) if doc else None

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        skip: int,
        limit: int,
        unread_only: bool = False,
    ) -> list[UserNotificationDocument]:
        query: dict[str, Any] = {"user_id": user_id}
        if unread_only:
            query["read_at"] = None
        cursor = (
            self._collection.find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        validated: list[UserNotificationDocument] = []
        for doc in docs:
            try:
                validated.append(UserNotificationDocument.model_validate(doc))
            except Exception as exc:  # noqa: BLE001s
                raise
        return validated

    async def count_for_user(
        self, user_id: UUID, *, unread_only: bool = False
    ) -> int:
        query: dict[str, Any] = {"user_id": user_id}
        if unread_only:
            query["read_at"] = None
        return await self._collection.count_documents(query)

    async def mark_read(
        self, notification_id: UUID, user_id: UUID
    ) -> UserNotificationDocument | None:
        now = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": notification_id, "user_id": user_id, "read_at": None},
            {"$set": {"read_at": now, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return UserNotificationDocument.model_validate(doc) if doc else None

    async def mark_all_read(self, user_id: UUID) -> int:
        now = utcnow()
        result = await self._collection.update_many(
            {"user_id": user_id, "read_at": None},
            {"$set": {"read_at": now, "updated_at": now}},
        )
        return result.modified_count


__all__ = [
    "NotificationCampaignsRepository",
    "NotificationGroupsRepository",
    "UserNotificationsRepository",
]
