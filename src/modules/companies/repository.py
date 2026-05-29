"""Data access for ``companies``. SKELETON."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.modules.companies.model import CompanyDocument

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class CompaniesRepository:
    COLLECTION: str = CompanyDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # TODO: unique index on (country, tax_id)
        raise NotImplementedError

    async def list(self, *, skip: int, limit: int) -> list[CompanyDocument]:
        raise NotImplementedError

    async def get(self, company_id: UUID) -> CompanyDocument | None:
        raise NotImplementedError

    async def create(self, doc: CompanyDocument) -> CompanyDocument:
        raise NotImplementedError

    async def update(
        self, company_id: UUID, patch: dict[str, object]
    ) -> CompanyDocument | None:
        raise NotImplementedError

    async def delete(self, company_id: UUID) -> bool:
        raise NotImplementedError


__all__ = ["CompaniesRepository"]
