"""Data access for ``blockchain_anchors``. SKELETON."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.modules.blockchain.model import AnchorStatus, BlockchainAnchorDocument

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class BlockchainRepository:
    COLLECTION: str = BlockchainAnchorDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # TODO: index on (subject_collection, subject_id) + unique (tx_hash sparse)
        raise NotImplementedError

    async def list(self, *, skip: int, limit: int) -> list[BlockchainAnchorDocument]:
        raise NotImplementedError

    async def get(self, anchor_id: UUID) -> BlockchainAnchorDocument | None:
        raise NotImplementedError

    async def create(self, doc: BlockchainAnchorDocument) -> BlockchainAnchorDocument:
        raise NotImplementedError

    async def update_status(
        self,
        anchor_id: UUID,
        *,
        status: AnchorStatus,
        tx_hash: str | None = None,
        block_number: int | None = None,
        raw: dict[str, object] | None = None,
    ) -> None:
        raise NotImplementedError


__all__ = ["BlockchainRepository"]
