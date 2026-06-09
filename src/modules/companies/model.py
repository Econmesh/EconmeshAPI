"""Persistence model for ``companies``."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.schemas.base import DomainDocument


class CompanyAddress(BaseModel):
    """Structured postal address for a company."""

    postal_code: str | None = Field(default=None, description="CEP / postal code.")
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class CompanyDocument(DomainDocument):
    """A company / legal entity owned by a platform user."""

    collection_name: ClassVar[str] = "companies"

    owner_user_id: UUID = Field(..., description="FK to users._id — creator/owner.")
    legal_name: str
    trade_name: str | None = None
    tax_id: str = Field(..., description="CNPJ / VAT / EIN — country-specific.")
    email: str | None = None
    phone: str | None = None
    address: CompanyAddress | None = None
    country: str = Field(default="BR", min_length=2, max_length=2)
    website: str | None = None
    description: str | None = None
    logo_storage_key: str | None = None
    logo_url: str | None = None
    sector: str | None = None
    is_active: bool = True


__all__ = ["CompanyAddress", "CompanyDocument"]
