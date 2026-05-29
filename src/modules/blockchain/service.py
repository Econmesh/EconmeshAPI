"""Business rules for blockchain anchoring. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.blockchain.repository import BlockchainRepository
from src.modules.blockchain.schema import AnchorRequest, AnchorResponse


class BlockchainService:
    def __init__(self, repository: BlockchainRepository) -> None:
        self._repo = repository
        # TODO: inject a BlockchainProvider implementation.

    async def list(self, *, page: int, page_size: int) -> list[AnchorResponse]:
        raise NotImplementedError("TODO: list anchors")

    async def get(self, anchor_id: UUID) -> AnchorResponse:
        raise NotImplementedError("TODO: fetch anchor")

    async def submit(self, payload: AnchorRequest) -> AnchorResponse:
        # TODO: enqueue anchoring job; return pending record immediately.
        raise NotImplementedError


__all__ = ["BlockchainService"]
