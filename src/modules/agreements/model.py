"""Persistence models for ``agreements`` and ``agreement_events``."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.schemas.base import DomainDocument
from src.shared.utils.ids import new_uuid


class AgreementStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_SEND = "awaiting_send"
    AWAITING_SIGNATURES = "awaiting_signatures"
    PARTIALLY_SIGNED = "partially_signed"
    SIGNED = "signed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SigningMode(StrEnum):
    UNORDERED = "unordered"
    ORDERED = "ordered"


class ParticipantKind(StrEnum):
    COMPANY = "company"
    EXTERNAL = "external"


class ParticipantRole(StrEnum):
    SIGN = "sign"
    APPROVE = "approve"
    WITNESS = "witness"
    ACKNOWLEDGE = "acknowledge"
    RECEIPT = "receipt"


class ParticipantStatus(StrEnum):
    PENDING = "pending"
    VIEWED = "viewed"
    COMPLETED = "completed"
    REJECTED = "rejected"


class FieldType(StrEnum):
    SIGNATURE = "signature"
    DATE = "date"
    NAME = "name"
    CPF = "cpf"
    JOB_TITLE = "job_title"
    COMPANY = "company"
    INITIALS = "initials"
    TEXT = "text"
    CHECKBOX = "checkbox"


class AgreementFilter(StrEnum):
    ALL = "all"
    SIGNED = "signed"
    PENDING = "pending"
    MINE = "mine"
    ORGANIZATION = "organization"
    COMPANY = "company"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AgreementSort(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"
    UPDATED = "updated"
    TITLE = "title"


class AgreementEventType(StrEnum):
    CREATED = "created"
    PARTICIPANT_ADDED = "participant_added"
    PARTICIPANTS_UPDATED = "participants_updated"
    FIELDS_UPDATED = "fields_updated"
    SENT = "sent"
    VIEWED = "viewed"
    OPENED = "opened"
    SIGNED = "signed"
    APPROVED = "approved"
    WITNESSED = "witnessed"
    ACKNOWLEDGED = "acknowledged"
    RECEIPT_CONFIRMED = "receipt_confirmed"
    REJECTED = "rejected"
    COMPLETED = "completed"
    DOWNLOADED = "downloaded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UPDATED = "updated"


class AgreementFile(BaseModel):
    storage_key: str
    url: str
    sha256: str
    filename: str
    page_count: int = 1
    size_bytes: int | None = None


class AgreementParticipant(BaseModel):
    id: UUID = Field(default_factory=new_uuid)
    kind: ParticipantKind
    user_id: UUID | None = None
    company_id: UUID | None = None
    company_name: str | None = None
    name: str
    email: str
    cpf: str | None = None
    job_title: str | None = None
    role: ParticipantRole = ParticipantRole.SIGN
    order_index: int = 0
    status: ParticipantStatus = ParticipantStatus.PENDING
    completed_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    signature_hash: str | None = None
    ip: str | None = None
    user_agent: str | None = None


class AgreementField(BaseModel):
    id: UUID = Field(default_factory=new_uuid)
    participant_id: UUID
    field_type: FieldType
    page: int = Field(..., ge=1)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)
    height: float = Field(..., gt=0, le=1)
    value: str | None = None


class AgreementDocument(DomainDocument):
    """Electronic agreement with participants and signature fields."""

    collection_name: ClassVar[str] = "agreements"

    title: str
    description: str | None = None
    deadline: datetime | None = None
    status: AgreementStatus = AgreementStatus.DRAFT
    company_id: UUID
    company_name: str
    owner_user_id: UUID
    signing_mode: SigningMode = SigningMode.UNORDERED
    original_file: AgreementFile | None = None
    signed_file: AgreementFile | None = None
    audit_report_file: AgreementFile | None = None
    certificate_file: AgreementFile | None = None
    chat_audit_report_file: AgreementFile | None = None
    opportunity_audit_report_file: AgreementFile | None = None
    participants: list[AgreementParticipant] = Field(default_factory=list)
    fields: list[AgreementField] = Field(default_factory=list)
    verification_code: str
    is_active: bool = True
    opportunity_id: UUID | None = None
    conversation_id: UUID | None = None
    contract_proposal_id: UUID | None = None


class AgreementEventDocument(DomainDocument):
    """Immutable audit trail entry for an agreement."""

    collection_name: ClassVar[str] = "agreement_events"

    agreement_id: UUID
    event_type: AgreementEventType
    actor_user_id: UUID | None = None
    actor_name: str | None = None
    actor_company_id: UUID | None = None
    actor_company_name: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "AgreementDocument",
    "AgreementEventDocument",
    "AgreementEventType",
    "AgreementField",
    "AgreementFile",
    "AgreementFilter",
    "AgreementParticipant",
    "AgreementSort",
    "AgreementStatus",
    "FieldType",
    "ParticipantKind",
    "ParticipantRole",
    "ParticipantStatus",
    "SigningMode",
]
