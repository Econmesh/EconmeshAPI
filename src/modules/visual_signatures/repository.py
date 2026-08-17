"""Mongo repositories for visual signatures and their audit events."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from src.core.exceptions import ConflictError
from src.modules.visual_signatures.model import (
    VisualSignatureDocument,
    VisualSignatureEventDocument,
    VisualSignatureKind,
    VisualSignatureSource,
)

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class VisualSignaturesRepository:
    COLLECTION: str = VisualSignatureDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("user_id", ASCENDING), ("kind", ASCENDING)],
            unique=True,
            name="uniq_user_kind",
        )
        await self._collection.create_index(
            [("uniqueness_hmac", ASCENDING)],
            unique=True,
            name="uniq_automatic_combo",
            partialFilterExpression={
                "source": VisualSignatureSource.AUTOMATIC.value,
                "uniqueness_hmac": {"$type": "string"},
            },
        )

    async def get(self, signature_id: UUID) -> VisualSignatureDocument | None:
        doc = await self._collection.find_one({"_id": signature_id})
        return VisualSignatureDocument.model_validate(doc) if doc else None

    async def get_for_user(
        self, user_id: UUID, kind: VisualSignatureKind
    ) -> VisualSignatureDocument | None:
        doc = await self._collection.find_one(
            {
                "user_id": user_id,
                "kind": kind.value if isinstance(kind, VisualSignatureKind) else kind,
            }
        )
        return VisualSignatureDocument.model_validate(doc) if doc else None

    async def list_for_user(self, user_id: UUID) -> list[VisualSignatureDocument]:
        cursor = self._collection.find({"user_id": user_id})
        docs = await cursor.to_list(length=4)
        return [VisualSignatureDocument.model_validate(doc) for doc in docs]

    async def uniqueness_taken(self, uniqueness_hmac: str) -> bool:
        doc = await self._collection.find_one(
            {"uniqueness_hmac": uniqueness_hmac},
            projection={"_id": 1},
        )
        return doc is not None

    async def create(self, doc: VisualSignatureDocument) -> VisualSignatureDocument:
        try:
            await self._collection.insert_one(doc.to_mongo())
        except DuplicateKeyError as exc:
            details = str(exc)
            if "uniq_automatic_combo" in details or "uniqueness_hmac" in details:
                raise ConflictError(
                    "Já existe uma assinatura gerada com esta combinação de "
                    "caracteres e fonte.",
                    code="visual_signature_not_unique",
                ) from exc
            raise ConflictError(
                "Você já possui este tipo de assinatura confirmada.",
                code="visual_signature_already_exists",
            ) from exc
        return doc


class VisualSignatureEventsRepository:
    COLLECTION: str = VisualSignatureEventDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("signature_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_signature_created_at",
        )
        await self._collection.create_index(
            [("user_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_user_created_at",
        )

    async def create(
        self, doc: VisualSignatureEventDocument
    ) -> VisualSignatureEventDocument:
        await self._collection.insert_one(doc.to_mongo())
        return doc


__all__ = ["VisualSignatureEventsRepository", "VisualSignaturesRepository"]
