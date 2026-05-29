"""Data access for the ``users`` collection."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, ReturnDocument

from src.modules.auth.model import UserDocument
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class AuthRepository:
    """Async repository encapsulating all Mongo access for users."""

    COLLECTION: str = UserDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    # ----------------------------------------------------------------- setup
    async def ensure_indexes(self) -> None:
        """Idempotently create indexes used by this collection."""
        await self._collection.create_index(
            [("firebase_uid", ASCENDING)], unique=True, name="uniq_firebase_uid"
        )
        await self._collection.create_index(
            [("email", ASCENDING)],
            unique=False,
            name="ix_email",
            sparse=True,
        )
        await self._collection.create_index(
            [("created_at", ASCENDING)], name="ix_created_at"
        )

    # -------------------------------------------------------------- queries
    async def get_by_firebase_uid(self, firebase_uid: str) -> UserDocument | None:
        doc = await self._collection.find_one({"firebase_uid": firebase_uid})
        return UserDocument.model_validate(doc) if doc else None

    async def get_by_id(self, user_id: UUID) -> UserDocument | None:
        doc = await self._collection.find_one({"_id": user_id})
        return UserDocument.model_validate(doc) if doc else None

    # -------------------------------------------------------------- mutations
    async def upsert_from_firebase(self, claims: dict[str, Any]) -> UserDocument:
        """Insert or update a user from Firebase claims; bumps ``last_login_at``."""
        firebase_uid = str(claims["uid"])
        now = utcnow()

        set_on_insert: dict[str, Any] = {
            "_id": new_uuid(),
            "firebase_uid": firebase_uid,
            "created_at": now,
            "is_active": True,
        }
        set_always: dict[str, Any] = {
            "email": claims.get("email"),
            "name": claims.get("name"),
            "picture": claims.get("picture"),
            "email_verified": bool(claims.get("email_verified", False)),
            "updated_at": now,
            "last_login_at": now,
            "custom_claims": {
                k: v
                for k, v in claims.items()
                if k
                not in {
                    "uid",
                    "email",
                    "name",
                    "picture",
                    "email_verified",
                    "iss",
                    "aud",
                    "exp",
                    "iat",
                    "auth_time",
                    "sub",
                    "firebase",
                }
            },
        }
        role = claims.get("role")
        if isinstance(role, str):
            set_always["role"] = role

        doc = await self._collection.find_one_and_update(
            {"firebase_uid": firebase_uid},
            {"$set": set_always, "$setOnInsert": set_on_insert},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return UserDocument.model_validate(doc)

    async def set_active(self, user_id: UUID, *, is_active: bool) -> bool:
        result = await self._collection.update_one(
            {"_id": user_id},
            {"$set": {"is_active": is_active, "updated_at": utcnow()}},
        )
        return result.modified_count > 0

    async def update_last_login(self, firebase_uid: str, *, when: datetime | None = None) -> None:
        await self._collection.update_one(
            {"firebase_uid": firebase_uid},
            {"$set": {"last_login_at": when or utcnow()}},
        )


__all__ = ["AuthRepository"]
