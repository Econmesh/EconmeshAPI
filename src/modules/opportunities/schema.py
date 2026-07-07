"""DTOs for the ``opportunities`` module."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from fastapi import Query
from pydantic import Field, HttpUrl, field_validator, model_validator

from src.modules.opportunities.model import (
    OfferDemand,
    OpportunityPeriodicity,
    OpportunitySort,
    OpportunityType,
)
from src.shared.schemas.base import APIModel

_MAX_IMAGES = 5


class OpportunityImageInput(APIModel):
    storage_key: str = Field(..., min_length=1, max_length=500)
    url: str = Field(..., min_length=1, max_length=1000)
    is_primary: bool = False
    sort_order: int = Field(default=0, ge=0)


class OpportunityImageResponse(APIModel):
    storage_key: str
    url: str
    is_primary: bool
    sort_order: int


class _OpportunityPayloadBase(APIModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=20, max_length=5000)
    opportunity_type: OpportunityType | None = None
    offer_demand: OfferDemand | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    technical_detail: str | None = Field(default=None, min_length=1, max_length=200)
    purity_percent: float | None = Field(default=None, ge=0, le=100)
    physical_state: str | None = Field(default=None, min_length=1, max_length=100)
    periodicity: OpportunityPeriodicity | None = None
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    price: float | None = Field(default=None, ge=0)
    price_negotiable: bool | None = None
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    latitude: float | None = None
    longitude: float | None = None
    images: list[OpportunityImageInput] | None = None

    @field_validator("state")
    @classmethod
    def _validate_state(cls, value: str | None) -> str | None:
        if value is not None and len(value) != 2:
            raise ValueError("State must be a 2-character UF code.")
        return value

    @field_validator("images")
    @classmethod
    def _validate_images_count(
        cls, value: list[OpportunityImageInput] | None
    ) -> list[OpportunityImageInput] | None:
        if value is not None and len(value) > _MAX_IMAGES:
            raise ValueError(f"At most {_MAX_IMAGES} images are allowed.")
        return value


class OpportunityCreate(_OpportunityPayloadBase):
    company_id: UUID
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=20, max_length=5000)
    opportunity_type: OpportunityType
    offer_demand: OfferDemand
    category: str = Field(..., min_length=1, max_length=100)
    technical_detail: str = Field(..., min_length=1, max_length=200)
    physical_state: str = Field(..., min_length=1, max_length=100)
    periodicity: OpportunityPeriodicity
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=50)
    price_negotiable: bool = False
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=2)
    images: list[OpportunityImageInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_price(self) -> OpportunityCreate:
        if self.price_negotiable:
            object.__setattr__(self, "price", None)
        elif self.price is None:
            raise ValueError(
                "Price is required unless price_negotiable is true."
            )
        return self


class OpportunityUpdate(_OpportunityPayloadBase):
    @model_validator(mode="after")
    def _validate_price(self) -> OpportunityUpdate:
        if self.price_negotiable is True:
            object.__setattr__(self, "price", None)
        elif self.price_negotiable is False and self.price is None:
            raise ValueError(
                "Price is required unless price_negotiable is true."
            )
        return self


class MatchPotential(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MatchDetails(APIModel):
    category: int = Field(..., ge=0, le=100)
    technical_detail: int = Field(..., ge=0, le=100)
    purity: int = Field(..., ge=0, le=100)
    physical_state: int = Field(..., ge=0, le=100)
    location: int = Field(..., ge=0, le=100)
    quantity: int = Field(..., ge=0, le=100)
    price: int = Field(..., ge=0, le=100)


class OpportunityMatch(APIModel):
    score: int = Field(..., ge=0, le=100)
    potential: MatchPotential
    details: MatchDetails
    matched_demand: "OpportunityResponse"


class OpportunityResponse(APIModel):
    id: UUID
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
    price_negotiable: bool
    city: str
    state: str
    latitude: float | None = None
    longitude: float | None = None
    images: list[OpportunityImageResponse]
    created_at: datetime
    updated_at: datetime
    matching: OpportunityMatch | None = None


class OpportunityListResponse(APIModel):
    items: list[OpportunityResponse]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    has_more: bool
    has_demands: bool = False


class OpportunityListParams(APIModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=200)
    q: str | None = None
    opportunity_type: OpportunityType | None = None
    offer_demand: OfferDemand | None = None
    category: str | None = None
    state: str | None = None
    city: str | None = None
    periodicity: OpportunityPeriodicity | None = None
    price_min: float | None = Field(default=None, ge=0)
    price_max: float | None = Field(default=None, ge=0)
    quantity_min: float | None = Field(default=None, ge=0)
    quantity_max: float | None = Field(default=None, ge=0)
    sort: OpportunitySort = OpportunitySort.NEWEST

    @classmethod
    def as_query(
        cls,
        page: int = Query(1, ge=1),
        page_size: int = Query(12, ge=1, le=200),
        q: str | None = Query(default=None),
        opportunity_type: OpportunityType | None = Query(default=None),
        offer_demand: OfferDemand | None = Query(default=None),
        category: str | None = Query(default=None),
        state: str | None = Query(default=None),
        city: str | None = Query(default=None),
        periodicity: OpportunityPeriodicity | None = Query(default=None),
        price_min: float | None = Query(default=None, ge=0),
        price_max: float | None = Query(default=None, ge=0),
        quantity_min: float | None = Query(default=None, ge=0),
        quantity_max: float | None = Query(default=None, ge=0),
        sort: OpportunitySort = Query(default=OpportunitySort.NEWEST),
    ) -> OpportunityListParams:
        return cls(
            page=page,
            page_size=page_size,
            q=q,
            opportunity_type=opportunity_type,
            offer_demand=offer_demand,
            category=category,
            state=state,
            city=city,
            periodicity=periodicity,
            price_min=price_min,
            price_max=price_max,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            sort=sort,
        )

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


class OpportunityImagePresignRequest(APIModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=3, max_length=100)


class OpportunityImagePresignResponse(APIModel):
    upload_url: HttpUrl
    storage_key: str
    public_url: str
    expires_at: datetime


__all__ = [
    "MatchDetails",
    "MatchPotential",
    "OpportunityCreate",
    "OpportunityImageInput",
    "OpportunityImagePresignRequest",
    "OpportunityImagePresignResponse",
    "OpportunityImageResponse",
    "OpportunityListParams",
    "OpportunityListResponse",
    "OpportunityMatch",
    "OpportunityResponse",
    "OpportunityUpdate",
]
