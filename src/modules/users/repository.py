"""Data access for ``user_profiles``."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, ReturnDocument

from src.modules.users.model import UserProfileDocument
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


def _bson_safe(value: Any) -> Any:
    """Convert values that BSON cannot encode (e.g. ``datetime.date``)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    if isinstance(value, dict):
        return {k: _bson_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_bson_safe(v) for v in value]
    return value


class UsersRepository:
    """Async repository for the ``user_profiles`` collection."""

    COLLECTION: str = UserProfileDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("user_id", ASCENDING)], unique=True, name="uniq_user_id"
        )

    async def get_by_user(self, user_id: UUID) -> UserProfileDocument | None:
        doc = await self._collection.find_one({"user_id": user_id})
        return UserProfileDocument.model_validate(doc) if doc else None

    async def create(self, doc: UserProfileDocument) -> UserProfileDocument:
        await self._collection.insert_one(_bson_safe(doc.to_mongo()))
        return doc

    async def upsert_for_user(
        self, user_id: UUID, patch: dict[str, object]
    ) -> UserProfileDocument:
        now = utcnow()
        set_on_insert: dict[str, object] = {
            "_id": new_uuid(),
            "user_id": user_id,
            "created_at": now,
            "locale": "pt-BR",
            "preferences": {},
            "country": "BR",
        }
        mongo_patch = _bson_safe({**patch, "updated_at": now})
        # MongoDB rejects the same path in both $set and $setOnInsert.
        for key in list(set_on_insert):
            if key in mongo_patch:
                del set_on_insert[key]

        # #region agent log
        try:
            import json as _json
            from pathlib import Path as _Path

            _bd = mongo_patch.get("birth_date")
            _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
            _log.open("a", encoding="utf-8").write(
                _json.dumps(
                    {
                        "sessionId": "bb369f",
                        "runId": "post-fix",
                        "hypothesisId": "A,B",
                        "location": "users/repository.py:upsert_for_user",
                        "message": "upsert about to write bson-safe patch",
                        "data": {
                            "birth_date_type": type(_bd).__name__ if _bd is not None else None,
                            "set_keys": sorted(mongo_patch.keys()),
                            "set_on_insert_keys": sorted(set_on_insert.keys()),
                            "overlap": sorted(
                                set(mongo_patch).intersection(set_on_insert)
                            ),
                        },
                        "timestamp": __import__("time").time() * 1000,
                    }
                )
                + "\n"
            )
        except Exception:
            pass
        # #endregion

        update: dict[str, object] = {"$set": mongo_patch}
        if set_on_insert:
            update["$setOnInsert"] = set_on_insert

        doc = await self._collection.find_one_and_update(
            {"user_id": user_id},
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return UserProfileDocument.model_validate(doc)

    async def delete_for_user(self, user_id: UUID) -> bool:
        result = await self._collection.delete_one({"user_id": user_id})
        return result.deleted_count > 0


__all__ = ["UsersRepository"]
