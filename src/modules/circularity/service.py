"""Business rules for circularity / ESG tracking. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.circularity.repository import CircularityRepository
from src.modules.circularity.schema import MaterialFlowCreate, MaterialFlowResponse


class CircularityService:
    def __init__(self, repository: CircularityRepository) -> None:
        self._repo = repository

    async def list_for_company(
        self, company_id: UUID, *, page: int, page_size: int
    ) -> list[MaterialFlowResponse]:
        raise NotImplementedError("TODO: list company flows")

    async def get(self, flow_id: UUID) -> MaterialFlowResponse:
        raise NotImplementedError("TODO: fetch flow")

    async def record_flow(self, payload: MaterialFlowCreate) -> MaterialFlowResponse:
        # TODO: persist + enqueue blockchain anchoring + emit audit event
        raise NotImplementedError


__all__ = ["CircularityService"]
