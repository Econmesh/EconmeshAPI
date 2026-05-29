"""HTTP controller for ``circularity``. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.circularity.schema import MaterialFlowCreate, MaterialFlowResponse
from src.modules.circularity.service import CircularityService


class CircularityController:
    def __init__(self, service: CircularityService) -> None:
        self._service = service

    async def list_for_company(
        self, company_id: UUID, page: int, page_size: int
    ) -> list[MaterialFlowResponse]:
        return await self._service.list_for_company(
            company_id, page=page, page_size=page_size
        )

    async def get(self, flow_id: UUID) -> MaterialFlowResponse:
        return await self._service.get(flow_id)

    async def record(self, payload: MaterialFlowCreate) -> MaterialFlowResponse:
        return await self._service.record_flow(payload)


__all__ = ["CircularityController"]
