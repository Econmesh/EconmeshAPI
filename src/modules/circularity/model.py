"""Persistence models for circularity / material-flow records."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument


class FlowType(StrEnum):
    GENERATION = "generation"
    COLLECTION = "collection"
    TRANSPORT = "transport"
    PROCESSING = "processing"
    RECYCLING = "recycling"
    DISPOSAL = "disposal"


class MaterialFlowDocument(DomainDocument):
    """A single material-flow event in the value chain."""

    collection_name: ClassVar[str] = "material_flows"

    company_id: UUID
    flow_type: FlowType
    material_code: str = Field(..., description="Standardised classification code.")
    quantity_kg: float = Field(..., ge=0)
    origin_location: str | None = None
    destination_location: str | None = None
    blockchain_anchor_tx: str | None = Field(
        default=None, description="On-chain anchor receipt (filled by worker)."
    )


__all__ = ["FlowType", "MaterialFlowDocument"]
