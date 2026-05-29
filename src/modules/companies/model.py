"""Persistence model for ``companies``."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from src.shared.schemas.base import DomainDocument


class CompanyDocument(DomainDocument):
    """A company / legal entity (industrial customer, recycler, broker)."""

    collection_name: ClassVar[str] = "companies"

    legal_name: str
    trade_name: str | None = None
    tax_id: str = Field(..., description="CNPJ / VAT / EIN — country-specific.")
    country: str = Field(..., min_length=2, max_length=2)
    sector: str | None = None
    is_active: bool = True


__all__ = ["CompanyDocument"]
