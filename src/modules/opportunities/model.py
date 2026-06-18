"""Persistence model for ``opportunities``."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.schemas.base import DomainDocument


class OpportunityType(StrEnum):
    COMERCIALIZACAO = "comercializacao"
    SIMBIOSE_INDUSTRIAL = "simbiose_industrial"
    COMPARTILHAMENTO = "compartilhamento"


class OfferDemand(StrEnum):
    GERADOR = "gerador"
    RECEPTOR = "receptor"


class OpportunityPeriodicity(StrEnum):
    CONTINUA = "continua"
    ESPORADICA = "esporadica"


class OpportunitySort(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    QUANTITY_DESC = "quantity_desc"


class OpportunityImage(BaseModel):
    storage_key: str
    url: str
    is_primary: bool = False
    sort_order: int = 0


class OpportunityDocument(DomainDocument):
    """A B2B circular-economy marketplace opportunity."""

    collection_name: ClassVar[str] = "opportunities"

    company_id: UUID
    company_name: str
    owner_user_id: UUID
    title: str
    description: str
    opportunity_type: OpportunityType
    offer_demand: OfferDemand
    category: str
    technical_detail: str
    purity_percent: float | None = None
    physical_state: str
    periodicity: OpportunityPeriodicity
    quantity: float
    unit: str
    price: float | None = None
    price_negotiable: bool = False
    city: str
    state: str
    latitude: float | None = None
    longitude: float | None = None
    images: list[OpportunityImage] = Field(default_factory=list)
    is_active: bool = True


__all__ = [
    "OfferDemand",
    "OpportunityDocument",
    "OpportunityImage",
    "OpportunityPeriodicity",
    "OpportunitySort",
    "OpportunityType",
]
