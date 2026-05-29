"""DTOs for the ``companies`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import APIModel


class CompanyCreate(APIModel):
    legal_name: str = Field(..., min_length=2)
    trade_name: str | None = None
    tax_id: str = Field(..., min_length=5)
    country: str = Field(..., min_length=2, max_length=2)
    sector: str | None = None


class CompanyUpdate(APIModel):
    legal_name: str | None = None
    trade_name: str | None = None
    sector: str | None = None
    is_active: bool | None = None


class CompanyResponse(APIModel):
    id: UUID
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    country: str
    sector: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


__all__ = ["CompanyCreate", "CompanyResponse", "CompanyUpdate"]
