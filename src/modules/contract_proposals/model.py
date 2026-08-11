"""Persistence models for contract proposals (minutas)."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.modules.contract_sections.model import ContractType
from src.shared.schemas.base import DomainDocument
from src.shared.utils.ids import new_uuid


class ContractProposalStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT_TO_AGREEMENTS = "sent_to_agreements"


class PartySnapshot(BaseModel):
    company_id: UUID
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    email: str | None = None
    phone: str | None = None
    legal_representative: str | None = None


class OpportunitySnapshot(BaseModel):
    opportunity_id: UUID
    title: str
    description: str
    category: str
    price: float | None = None
    price_negotiable: bool = False
    periodicity: str | None = None
    prazo: str | None = None


class ProposalSection(BaseModel):
    id: UUID = Field(default_factory=new_uuid)
    title: str
    content_html: str
    sort_order: int = 0
    is_core: bool = False
    is_admin_managed: bool = False
    is_editable: bool = True
    template_id: UUID | None = None


class ProposalPdfFile(BaseModel):
    storage_key: str
    url: str
    sha256: str
    filename: str
    page_count: int = 1
    size_bytes: int | None = None


class ContractProposalDocument(DomainDocument):
    """Editable contract draft linked to an opportunity conversation."""

    collection_name: ClassVar[str] = "contract_proposals"

    conversation_id: UUID
    opportunity_id: UUID
    offerer_company_id: UUID
    interested_company_id: UUID
    offerer_user_id: UUID
    interested_user_id: UUID
    created_by_user_id: UUID

    title: str
    contract_type: ContractType = ContractType.SERVICO
    status: ContractProposalStatus = ContractProposalStatus.DRAFT

    contractor: PartySnapshot  # interessada (contratante)
    contracted: PartySnapshot  # ofertante (contratada)
    opportunity: OpportunitySnapshot

    sections: list[ProposalSection] = Field(default_factory=list)
    pdf_file: ProposalPdfFile | None = None

    agreement_id: UUID | None = None
    change_request_message: str | None = None
    rejection_reason: str | None = None
    is_active: bool = True


__all__ = [
    "ContractProposalDocument",
    "ContractProposalStatus",
    "OpportunitySnapshot",
    "PartySnapshot",
    "ProposalPdfFile",
    "ProposalSection",
]
