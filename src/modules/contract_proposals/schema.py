"""DTOs for the ``contract_proposals`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Query
from pydantic import Field

from src.modules.contract_proposals.model import ContractProposalStatus
from src.modules.contract_sections.model import ContractType
from src.modules.platform_settings.model import ForoFillMode
from src.shared.schemas.base import APIModel


class PartySnapshotInput(APIModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=300)
    trade_name: str | None = Field(default=None, max_length=300)
    tax_id: str | None = Field(default=None, min_length=8, max_length=32)
    address_line: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=2)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    legal_representative: str | None = Field(default=None, max_length=200)


class OpportunitySnapshotInput(APIModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    category: str | None = Field(default=None, max_length=120)
    price: float | None = Field(default=None, ge=0)
    price_negotiable: bool | None = None
    periodicity: str | None = Field(default=None, max_length=80)
    prazo: str | None = Field(default=None, max_length=300)
    opportunity_type: str | None = Field(default=None, max_length=80)


class ProposalSectionInput(APIModel):
    id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=200)
    content_html: str = Field(..., min_length=1, max_length=50_000)
    sort_order: int = Field(default=0, ge=0)
    is_core: bool = False
    is_admin_managed: bool = False
    is_editable: bool = True
    template_id: UUID | None = None


class ContractProposalCreate(APIModel):
    conversation_id: UUID
    contract_type: ContractType | None = None


class ContractProposalUpdate(APIModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    contract_type: ContractType | None = None
    contractor: PartySnapshotInput | None = None
    contracted: PartySnapshotInput | None = None
    opportunity: OpportunitySnapshotInput | None = None
    sections: list[ProposalSectionInput] | None = None
    foro_city: str | None = Field(default=None, max_length=120)
    foro_state: str | None = Field(default=None, max_length=2)


class ProposalPdfFileResponse(APIModel):
    storage_key: str
    url: str
    sha256: str
    filename: str
    page_count: int
    size_bytes: int | None = None


class PartySnapshotResponse(APIModel):
    company_id: UUID
    legal_name: str
    trade_name: str | None
    tax_id: str
    address_line: str | None
    city: str | None
    state: str | None
    email: str | None
    phone: str | None
    legal_representative: str | None


class OpportunitySnapshotResponse(APIModel):
    opportunity_id: UUID
    title: str
    description: str
    category: str
    price: float | None
    price_negotiable: bool
    periodicity: str | None
    prazo: str | None
    opportunity_type: str | None = None


class ProposalSectionResponse(APIModel):
    id: UUID
    title: str
    content_html: str
    sort_order: int
    is_core: bool
    is_admin_managed: bool = False
    is_editable: bool = True
    template_id: UUID | None = None


class ContractProposalResponse(APIModel):
    id: UUID
    conversation_id: UUID
    opportunity_id: UUID
    offerer_company_id: UUID
    interested_company_id: UUID
    offerer_user_id: UUID
    interested_user_id: UUID
    created_by_user_id: UUID
    title: str
    contract_type: ContractType
    status: ContractProposalStatus
    contractor: PartySnapshotResponse
    contracted: PartySnapshotResponse
    opportunity: OpportunitySnapshotResponse
    sections: list[ProposalSectionResponse]
    foro_city: str | None = None
    foro_state: str | None = None
    foro_fill_mode: ForoFillMode = ForoFillMode.COMPANY
    pdf_file: ProposalPdfFileResponse | None
    agreement_id: UUID | None
    change_request_message: str | None
    rejection_reason: str | None
    my_role: str | None = None
    created_at: datetime
    updated_at: datetime


class ContractProposalListItem(APIModel):
    id: UUID
    conversation_id: UUID
    opportunity_id: UUID
    title: str
    status: ContractProposalStatus
    contract_type: ContractType
    opportunity_type: str | None = None
    agreement_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ContractProposalListResponse(APIModel):
    items: list[ContractProposalListItem]
    total: int
    page: int
    page_size: int


class ContractProposalListParams(APIModel):
    conversation_id: UUID | None = None
    page: int = 1
    page_size: int = 20

    @classmethod
    def as_query(
        cls,
        conversation_id: UUID | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> ContractProposalListParams:
        return cls(
            conversation_id=conversation_id,
            page=page,
            page_size=page_size,
        )


class RequestChangesRequest(APIModel):
    message: str = Field(..., min_length=2, max_length=5000)


class RejectProposalRequest(APIModel):
    reason: str = Field(..., min_length=2, max_length=5000)


class ApproveProposalResponse(APIModel):
    proposal: ContractProposalResponse
    agreement_id: UUID


__all__ = [
    "ApproveProposalResponse",
    "ContractProposalCreate",
    "ContractProposalListItem",
    "ContractProposalListParams",
    "ContractProposalListResponse",
    "ContractProposalResponse",
    "ContractProposalUpdate",
    "OpportunitySnapshotInput",
    "OpportunitySnapshotResponse",
    "PartySnapshotInput",
    "PartySnapshotResponse",
    "ProposalPdfFileResponse",
    "ProposalSectionInput",
    "ProposalSectionResponse",
    "RejectProposalRequest",
    "RequestChangesRequest",
]
