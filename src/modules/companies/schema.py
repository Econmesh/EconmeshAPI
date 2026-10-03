"""DTOs for the ``companies`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, HttpUrl, field_validator

from src.modules.companies.model import CompanyRegistrationStatus, ComplianceDocumentStatus
from src.shared.schemas.base import APIModel


class CompanyAddressInput(APIModel):
    postal_code: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class CompanyAddressResponse(APIModel):
    postal_code: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class CompanyComplianceFileResponse(APIModel):
    storage_key: str
    public_url: str
    filename: str
    content_type: str
    status: ComplianceDocumentStatus = ComplianceDocumentStatus.PENDING
    rejection_reason: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None


class CompanyDocumentReject(APIModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class CompanyCreate(APIModel):
    legal_name: str = Field(..., min_length=2, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    tax_id: str = Field(..., min_length=5, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    legal_representative: str | None = Field(default=None, max_length=200)
    address: CompanyAddressInput | None = None
    country: str = Field(default="BR", min_length=2, max_length=2)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    logo_storage_key: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=1000)
    sector: str | None = Field(default=None, max_length=100)


class CompanyUpdate(APIModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    legal_representative: str | None = Field(default=None, max_length=200)
    address: CompanyAddressInput | None = None
    website: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    logo_storage_key: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=1000)
    sector: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class CompanyResponse(APIModel):
    id: UUID
    owner_user_id: UUID | None = None
    registration_status: CompanyRegistrationStatus = CompanyRegistrationStatus.COMPLETE
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    email: str | None = None
    phone: str | None = None
    legal_representative: str | None = None
    address: CompanyAddressResponse | None = None
    country: str
    website: str | None = None
    description: str | None = None
    logo_storage_key: str | None = None
    logo_url: str | None = None
    sector: str | None = None
    operating_license: CompanyComplianceFileResponse | None = None
    mtr_document: CompanyComplianceFileResponse | None = None
    signature_authorization: CompanyComplianceFileResponse | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PreRegistrationCreate(APIModel):
    """Dados mínimos para o pré-cadastro de uma empresa (sem usuário/login)."""

    legal_name: str = Field(..., min_length=2, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    tax_id: str = Field(..., min_length=14, max_length=20, description="CNPJ.")
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    legal_representative: str | None = Field(default=None, max_length=200)
    address: CompanyAddressInput | None = None
    country: str = Field(default="BR", min_length=2, max_length=2)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    sector: str | None = Field(default=None, max_length=100)

    @field_validator("legal_name")
    @classmethod
    def _legal_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("legal_name must not be blank")
        return v.strip()

    @field_validator("tax_id")
    @classmethod
    def _digits_only_tax_id(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 14:
            raise ValueError("tax_id must be a 14-digit CNPJ")
        return digits

    @field_validator(
        "trade_name", "email", "phone", "legal_representative", "website", "description", "sector"
    )
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None


class PreRegistrationUpdate(APIModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, min_length=14, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    legal_representative: str | None = Field(default=None, max_length=200)
    address: CompanyAddressInput | None = None
    website: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    sector: str | None = Field(default=None, max_length=100)

    @field_validator("tax_id")
    @classmethod
    def _digits_only_tax_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 14:
            raise ValueError("tax_id must be a 14-digit CNPJ")
        return digits


class PreRegistrationMatch(APIModel):
    """Resultado público da busca de pré-cadastros (dados resumidos)."""

    id: UUID
    legal_name: str
    trade_name: str | None = None
    tax_id_masked: str
    city: str | None = None
    state: str | None = None


class PreRegistrationMatchList(APIModel):
    items: list[PreRegistrationMatch]


class PreRegistrationPrefill(APIModel):
    """Dados usados para preencher o formulário de cadastro."""

    id: UUID
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    email: str | None = None
    phone: str | None = None
    address: CompanyAddressResponse | None = None
    country: str


class LogoPresignRequest(APIModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=3, max_length=100)


class LogoPresignResponse(APIModel):
    upload_url: HttpUrl
    storage_key: str
    public_url: str
    expires_at: datetime


__all__ = [
    "CompanyAddressInput",
    "CompanyAddressResponse",
    "CompanyComplianceFileResponse",
    "CompanyCreate",
    "CompanyDocumentReject",
    "CompanyResponse",
    "CompanyUpdate",
    "LogoPresignRequest",
    "LogoPresignResponse",
    "PreRegistrationCreate",
    "PreRegistrationMatch",
    "PreRegistrationMatchList",
    "PreRegistrationPrefill",
    "PreRegistrationUpdate",
]
