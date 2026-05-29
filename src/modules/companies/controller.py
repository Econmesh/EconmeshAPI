"""HTTP controller for ``companies``. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.companies.schema import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)
from src.modules.companies.service import CompaniesService


class CompaniesController:
    def __init__(self, service: CompaniesService) -> None:
        self._service = service

    async def list(self, page: int, page_size: int) -> list[CompanyResponse]:
        return await self._service.list(page=page, page_size=page_size)

    async def get(self, company_id: UUID) -> CompanyResponse:
        return await self._service.get(company_id)

    async def create(self, payload: CompanyCreate) -> CompanyResponse:
        return await self._service.create(payload)

    async def update(self, company_id: UUID, payload: CompanyUpdate) -> CompanyResponse:
        return await self._service.update(company_id, payload)

    async def delete(self, company_id: UUID) -> None:
        await self._service.delete(company_id)


__all__ = ["CompaniesController"]
