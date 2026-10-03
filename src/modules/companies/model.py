"""Persistence model for ``companies``."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.shared.schemas.base import DomainDocument


class ComplianceDocumentStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CompanyRegistrationStatus(StrEnum):
    PRE_REGISTERED = "pre_registered"
    COMPLETE = "complete"


class CompanyAddress(BaseModel):
    """Structured postal address for a company."""

    postal_code: str | None = Field(default=None, description="CEP / postal code.")
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class CompanyComplianceFile(BaseModel):
    """A compliance document stored in Firebase Storage."""

    model_config = ConfigDict(use_enum_values=True)

    storage_key: str
    public_url: str
    filename: str
    content_type: str
    status: ComplianceDocumentStatus = ComplianceDocumentStatus.PENDING
    rejection_reason: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None


class CompanyDocument(DomainDocument):
    """A company / legal entity, optionally owned by a platform user."""

    collection_name: ClassVar[str] = "companies"

    owner_user_id: UUID | None = Field(
        default=None, description="FK to users._id — creator/owner. Null for pre-registration."
    )
    registration_status: CompanyRegistrationStatus = CompanyRegistrationStatus.COMPLETE
    legal_name: str
    trade_name: str | None = None
    tax_id: str = Field(..., description="CNPJ / VAT / EIN — country-specific.")
    email: str | None = None
    phone: str | None = None
    legal_representative: str | None = Field(
        default=None, description="Nome do responsável legal."
    )
    address: CompanyAddress | None = None
    country: str = Field(default="BR", min_length=2, max_length=2)
    website: str | None = None
    description: str | None = None
    logo_storage_key: str | None = None
    logo_url: str | None = None
    sector: str | None = None
    operating_license: CompanyComplianceFile | None = Field(
        default=None, description="Licença de operação ambiental."
    )
    mtr_document: CompanyComplianceFile | None = Field(
        default=None, description="Comprovante de cadastro no MTR Nacional (SINIR)."
    )
    signature_authorization: CompanyComplianceFile | None = Field(
        default=None,
        description="Procuração / autorização de assinatura em nome da empresa.",
    )
    is_active: bool = True


def is_pre_registered(company: CompanyDocument | None) -> bool:
    """True for an active pre-registration not yet claimed by a user."""
    return (
        company is not None
        and company.is_active
        and company.owner_user_id is None
        and company.registration_status == CompanyRegistrationStatus.PRE_REGISTERED
    )


__all__ = [
    "CompanyAddress",
    "CompanyComplianceFile",
    "CompanyDocument",
    "CompanyRegistrationStatus",
    "ComplianceDocumentStatus",
    "is_pre_registered",
]
