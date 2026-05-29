"""DTOs for the ``circularity`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.circularity.model import FlowType
from src.shared.schemas.base import APIModel


class MaterialFlowCreate(APIModel):
    company_id: UUID
    flow_type: FlowType
    material_code: str
    quantity_kg: float = Field(..., ge=0)
    origin_location: str | None = None
    destination_location: str | None = None


class MaterialFlowResponse(APIModel):
    id: UUID
    company_id: UUID
    flow_type: FlowType
    material_code: str
    quantity_kg: float
    origin_location: str | None = None
    destination_location: str | None = None
    blockchain_anchor_tx: str | None = None
    created_at: datetime
    updated_at: datetime


__all__ = ["MaterialFlowCreate", "MaterialFlowResponse"]
