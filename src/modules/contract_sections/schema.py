"""DTOs for the ``contract_sections`` module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from src.modules.contract_sections.model import SectionAppliesTo
from src.modules.opportunities.model import OpportunityType
from src.shared.schemas.base import APIModel


class ContractSectionCreate(APIModel):
    title: str = Field(..., min_length=2, max_length=200)
    content_html: str = Field(..., min_length=1, max_length=50_000)
    contract_type: SectionAppliesTo = SectionAppliesTo.TODOS
    opportunity_types: list[OpportunityType] = Field(
        default_factory=lambda: list(OpportunityType),
        min_length=1,
    )
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True
    is_company_editable: bool = False


class ContractSectionUpdate(APIModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    content_html: str | None = Field(default=None, min_length=1, max_length=50_000)
    contract_type: SectionAppliesTo | None = None
    opportunity_types: list[OpportunityType] | None = Field(default=None, min_length=1)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    is_company_editable: bool | None = None


class ContractSectionReorder(APIModel):
    ordered_ids: list[UUID] = Field(..., min_length=1)


class SystemSectionInfo(APIModel):
    key: str
    title: str
    description: str
    sort_order: int
    is_system: bool = True
    can_edit: bool = False
    can_delete: bool = False
    can_reorder: bool = False
    placement: Literal["start", "end"] = "start"


class MinutaStructureResponse(APIModel):
    system_sections: list[SystemSectionInfo]
    admin_sections: list[ContractSectionResponse]


class ContractPreviewSection(APIModel):
    title: str
    content_html: str
    is_system: bool = False


class ContractPreviewResponse(APIModel):
    opportunity_type: OpportunityType
    title: str
    html: str
    sections: list[ContractPreviewSection]


class ContractSectionResponse(APIModel):
    id: UUID
    title: str
    content_html: str
    contract_type: SectionAppliesTo
    opportunity_types: list[OpportunityType] = Field(default_factory=list)
    sort_order: int
    created_by: UUID
    is_active: bool
    is_company_editable: bool
    created_at: datetime
    updated_at: datetime


class ContractSectionListResponse(APIModel):
    items: list[ContractSectionResponse]
    total: int
    page: int
    page_size: int


__all__ = [
    "ContractPreviewResponse",
    "ContractPreviewSection",
    "ContractSectionCreate",
    "ContractSectionListResponse",
    "ContractSectionReorder",
    "ContractSectionResponse",
    "ContractSectionUpdate",
    "MinutaStructureResponse",
    "SystemSectionInfo",
]
