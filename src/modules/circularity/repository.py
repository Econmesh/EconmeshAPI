"""Data access for material-flow records. SKELETON."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.modules.circularity.model import MaterialFlowDocument

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class CircularityRepository:
    COLLECTION: str = MaterialFlowDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # TODO: index on (company_id, created_at), text index on material_code
        raise NotImplementedError

    async def list_for_company(
        self, company_id: UUID, *, skip: int, limit: int
    ) -> list[MaterialFlowDocument]:
        raise NotImplementedError

    async def get(self, flow_id: UUID) -> MaterialFlowDocument | None:
        raise NotImplementedError

    async def create(self, doc: MaterialFlowDocument) -> MaterialFlowDocument:
        raise NotImplementedError

    async def set_anchor(self, flow_id: UUID, tx_hash: str) -> None:
        raise NotImplementedError


__all__ = ["CircularityRepository"]
