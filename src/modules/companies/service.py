"""Business rules for ``companies``. SKELETON."""

from __future__ import annotations

from uuid import UUID

from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.schema import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)


class CompaniesService:
    def __init__(self, repository: CompaniesRepository) -> None:
        self._repo = repository

    async def list(self, *, page: int, page_size: int) -> list[CompanyResponse]:
        raise NotImplementedError("TODO: list companies")

    async def get(self, company_id: UUID) -> CompanyResponse:
        raise NotImplementedError("TODO: fetch company")

    async def create(self, payload: CompanyCreate) -> CompanyResponse:
        raise NotImplementedError("TODO: create company")

    async def update(self, company_id: UUID, payload: CompanyUpdate) -> CompanyResponse:
        raise NotImplementedError("TODO: update company")

    async def delete(self, company_id: UUID) -> None:
        raise NotImplementedError("TODO: soft-delete company")


__all__ = ["CompaniesService"]
