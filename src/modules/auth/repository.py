"""Data access for the ``users`` and ``email_verifications`` collections."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, ReturnDocument

from src.modules.auth.model import EmailVerificationDocument, UserDocument
from src.shared.constants.roles import Role
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
            unique=True,
            name="uniq_email",
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

    async def get_by_email(self, email: str) -> UserDocument | None:
        doc = await self._collection.find_one({"email": email})
        return UserDocument.model_validate(doc) if doc else None

    # -------------------------------------------------------------- mutations
    async def create_user(self, user: UserDocument) -> UserDocument:
        """Insert a fully-formed user document (used by the registration flow)."""
        await self._collection.insert_one(user.to_mongo())
        return user

    async def upsert_from_firebase(self, claims: dict[str, Any]) -> UserDocument:
        """Insert or update a user from Firebase claims; bumps ``last_login_at``."""
        firebase_uid = str(claims["uid"])
        now = utcnow()

        set_on_insert: dict[str, Any] = {
            "_id": new_uuid(),
            "firebase_uid": firebase_uid,
            "created_at": now,
            "is_active": True,
            # Trust Firebase's verification state for the seed value; our own
            # confirmation flow flips this for email/password sign-ups.
            "is_verified": bool(claims.get("email_verified", False)),
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

    async def mark_verified(self, user_id: UUID) -> bool:
        """Flag the account as confirmed (login gate) and email-verified."""
        result = await self._collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "is_verified": True,
                    "email_verified": True,
                    "updated_at": utcnow(),
                }
            },
        )
        return result.modified_count > 0

    async def set_role(self, user_id: UUID, *, role: Role) -> bool:
        result = await self._collection.update_one(
            {"_id": user_id},
            {"$set": {"role": role.value, "updated_at": utcnow()}},
        )
        return result.modified_count > 0

    async def update_last_login(self, firebase_uid: str, *, when: datetime | None = None) -> None:
        await self._collection.update_one(
            {"firebase_uid": firebase_uid},
            {"$set": {"last_login_at": when or utcnow()}},
        )

    async def update_profile(
        self, user_id: UUID, patch: dict[str, object]
    ) -> UserDocument | None:
        patch["updated_at"] = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": user_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return UserDocument.model_validate(doc) if doc else None


class EmailVerificationRepository:
    """Async repository for single-use account-confirmation tokens."""

    COLLECTION: str = EmailVerificationDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("token_hash", ASCENDING)], unique=True, name="uniq_token_hash"
        )
        await self._collection.create_index(
            [("user_id", ASCENDING)], name="ix_user_id"
        )
        # TTL index: Mongo purges expired tokens automatically.
        await self._collection.create_index(
            [("expires_at", ASCENDING)], name="ttl_expires_at", expireAfterSeconds=0
        )

    async def create(self, doc: EmailVerificationDocument) -> EmailVerificationDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc

    async def get_by_token_hash(self, token_hash: str) -> EmailVerificationDocument | None:
        doc = await self._collection.find_one({"token_hash": token_hash})
        return EmailVerificationDocument.model_validate(doc) if doc else None

    async def consume(self, verification_id: UUID) -> bool:
        result = await self._collection.update_one(
            {"_id": verification_id, "consumed_at": None},
            {"$set": {"consumed_at": utcnow()}},
        )
        return result.modified_count > 0

    async def delete_for_user(self, user_id: UUID) -> int:
        result = await self._collection.delete_many({"user_id": user_id})
        return result.deleted_count


__all__ = ["AuthRepository", "EmailVerificationRepository"]
