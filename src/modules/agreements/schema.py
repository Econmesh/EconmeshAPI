"""DTOs for the ``agreements`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Query
from pydantic import EmailStr, Field

from src.modules.agreements.model import (
    AgreementFilter,
    AgreementSort,
    AgreementStatus,
    FieldType,
    ParticipantKind,
    ParticipantRole,
    ParticipantStatus,
    SigningMode,
)
from src.shared.schemas.base import APIModel


class AgreementFileResponse(APIModel):
    storage_key: str
    url: str
    sha256: str
    filename: str
    page_count: int
    size_bytes: int | None = None


class ParticipantInput(APIModel):
    kind: ParticipantKind
    company_id: UUID | None = None
    company_name: str | None = Field(default=None, max_length=200)
    name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    cpf: str | None = Field(default=None, max_length=14)
    job_title: str | None = Field(default=None, max_length=120)
    role: ParticipantRole = ParticipantRole.SIGN
    order_index: int = Field(default=0, ge=0)


class ParticipantResponse(APIModel):
    id: UUID
    kind: ParticipantKind
    user_id: UUID | None = None
    company_id: UUID | None = None
    company_name: str | None = None
    name: str
    email: str
    cpf: str | None = None
    job_title: str | None = None
    role: ParticipantRole
    order_index: int
    status: ParticipantStatus
    completed_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None


class FieldInput(APIModel):
    id: UUID | None = None
    participant_id: UUID
    field_type: FieldType
    page: int = Field(..., ge=1)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)
    height: float = Field(..., gt=0, le=1)
    value: str | None = None


class FieldResponse(APIModel):
    id: UUID
    participant_id: UUID
    field_type: FieldType
    page: int
    x: float
    y: float
    width: float
    height: float
    value: str | None = None


class AgreementCreate(APIModel):
    title: str = Field(..., min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    deadline: datetime | None = None
    company_id: UUID
    signing_mode: SigningMode = SigningMode.UNORDERED


class AgreementUpdate(APIModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    deadline: datetime | None = None
    signing_mode: SigningMode | None = None


class ParticipantsUpdate(APIModel):
    signing_mode: SigningMode | None = None
    participants: list[ParticipantInput] = Field(..., min_length=1)


class FieldsUpdate(APIModel):
    fields: list[FieldInput] = Field(default_factory=list)


class SignRequest(APIModel):
    field_values: dict[str, str] = Field(
        default_factory=dict,
        description="Map of field_id -> value for text/checkbox fields.",
    )
    signature_data: str | None = Field(
        default=None,
        description="Optional drawn signature payload (data URL or text).",
    )


class RejectRequest(APIModel):
    reason: str = Field(..., min_length=2, max_length=2000)


class AgreementListItem(APIModel):
    id: UUID
    title: str
    status: AgreementStatus
    company_id: UUID
    company_name: str
    owner_user_id: UUID
    signing_mode: SigningMode
    deadline: datetime | None = None
    participants: list[ParticipantResponse]
    signed_count: int
    total_participants: int
    progress_percent: int
    verification_code: str
    created_at: datetime
    updated_at: datetime


class AgreementResponse(APIModel):
    id: UUID
    title: str
    description: str | None = None
    deadline: datetime | None = None
    status: AgreementStatus
    company_id: UUID
    company_name: str
    owner_user_id: UUID
    signing_mode: SigningMode
    original_file: AgreementFileResponse | None = None
    signed_file: AgreementFileResponse | None = None
    audit_report_file: AgreementFileResponse | None = None
    certificate_file: AgreementFileResponse | None = None
    chat_audit_report_file: AgreementFileResponse | None = None
    opportunity_audit_report_file: AgreementFileResponse | None = None
    participants: list[ParticipantResponse]
    fields: list[FieldResponse]
    verification_code: str
    signed_count: int
    total_participants: int
    progress_percent: int
    created_at: datetime
    updated_at: datetime


class AgreementListResponse(APIModel):
    items: list[AgreementListItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class AgreementListParams(APIModel):
    q: str | None = None
    filter: AgreementFilter = AgreementFilter.ALL
    sort: AgreementSort = AgreementSort.NEWEST
    company_id: UUID | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size

    @classmethod
    def as_query(
        cls,
        q: str | None = Query(None),
        filter: AgreementFilter = Query(AgreementFilter.ALL),
        sort: AgreementSort = Query(AgreementSort.NEWEST),
        company_id: UUID | None = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> AgreementListParams:
        return cls(
            q=q,
            filter=filter,
            sort=sort,
            company_id=company_id,
            page=page,
            page_size=page_size,
        )


class TimelineEventResponse(APIModel):
    id: UUID
    agreement_id: UUID
    event_type: str
    actor_user_id: UUID | None = None
    actor_name: str | None = None
    actor_company_id: UUID | None = None
    actor_company_name: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    metadata: dict[str, str]
    created_at: datetime


class TimelineResponse(APIModel):
    items: list[TimelineEventResponse]


class ProgressResponse(APIModel):
    total_participants: int
    completed: int
    pending: int
    rejected: int
    viewed: int
    progress_percent: int
    pending_participants: list[ParticipantResponse]
    rejected_participants: list[ParticipantResponse]
    viewed_participants: list[ParticipantResponse]
    completed_participants: list[ParticipantResponse]


class EligibilityMissing(APIModel):
    code: str = "profile_incomplete"
    missing: list[str]
    message: str


class CompanySearchItem(APIModel):
    id: UUID
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    email: str | None = None
    phone: str | None = None
    legal_representative: str | None = None
    owner_user_id: UUID
    owner_name: str | None = None
    owner_email: str | None = None
    owner_cpf: str | None = None
    owner_job_title: str | None = None


class CompanySearchResponse(APIModel):
    items: list[CompanySearchItem]


class DownloadUrlResponse(APIModel):
    url: str
    artifact: str


__all__ = [
    "AgreementCreate",
    "AgreementFileResponse",
    "AgreementListItem",
    "AgreementListParams",
    "AgreementListResponse",
    "AgreementResponse",
    "AgreementUpdate",
    "CompanySearchItem",
    "CompanySearchResponse",
    "DownloadUrlResponse",
    "EligibilityMissing",
    "FieldInput",
    "FieldResponse",
    "FieldsUpdate",
    "ParticipantInput",
    "ParticipantResponse",
    "ParticipantsUpdate",
    "ProgressResponse",
    "RejectRequest",
    "SignRequest",
    "TimelineEventResponse",
    "TimelineResponse",
]
