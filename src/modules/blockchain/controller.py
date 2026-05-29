"""HTTP controller for ``blockchain``. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.blockchain.schema import AnchorRequest, AnchorResponse
from src.modules.blockchain.service import BlockchainService


class BlockchainController:
    def __init__(self, service: BlockchainService) -> None:
        self._service = service

    async def list(self, page: int, page_size: int) -> list[AnchorResponse]:
        return await self._service.list(page=page, page_size=page_size)

    async def get(self, anchor_id: UUID) -> AnchorResponse:
        return await self._service.get(anchor_id)

    async def submit(self, payload: AnchorRequest) -> AnchorResponse:
        return await self._service.submit(payload)


__all__ = ["BlockchainController"]
