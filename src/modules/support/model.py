"""Persistence models for support tickets."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument

# Sentinel author id for messages sent by unauthenticated site visitors.
VISITOR_AUTHOR_ID = UUID("00000000-0000-0000-0000-000000000001")


class SupportTicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class SupportTicketSource(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    CONTACT_REQUEST = "contact_request"
    DOCUMENT_REVIEW = "document_review"


class SupportContactInterest(StrEnum):
    DMC = "dmc"
    MRI = "mri"


class SupportAuthorRole(StrEnum):
    USER = "user"
    ADMIN = "admin"
    VISITOR = "visitor"


class SupportMessageType(StrEnum):
    USER_MESSAGE = "user_message"
    ADMIN_REPLY = "admin_reply"
    INTERNAL_NOTE = "internal_note"


VISITOR_TICKET_SOURCES = frozenset(
    {
        SupportTicketSource.EXTERNAL,
        SupportTicketSource.CONTACT_REQUEST,
    }
)


class SupportTicketDocument(DomainDocument):
    collection_name: ClassVar[str] = "support_tickets"

    source: SupportTicketSource = SupportTicketSource.INTERNAL
    user_id: UUID | None = None
    company_id: UUID | None = None
    visitor_email: str | None = None
    visitor_name: str | None = None
    company: str | None = None
    position: str | None = None
    phone: str | None = None
    address: str | None = None
    interest: SupportContactInterest | None = None
    ticket_number: int
    subject: str
    status: SupportTicketStatus = SupportTicketStatus.OPEN
    assigned_admin_id: UUID | None = None
    closed_by: UUID | None = None
    closed_at: datetime | None = None
    last_message_at: datetime | None = None
    last_responder_admin_id: UUID | None = None


class SupportMessageDocument(DomainDocument):
    collection_name: ClassVar[str] = "support_messages"

    ticket_id: UUID
    author_id: UUID
    author_role: SupportAuthorRole
    message_type: SupportMessageType
    body: str
    read_at: datetime | None = None


__all__ = [
    "VISITOR_AUTHOR_ID",
    "VISITOR_TICKET_SOURCES",
    "SupportAuthorRole",
    "SupportContactInterest",
    "SupportMessageDocument",
    "SupportMessageType",
    "SupportTicketDocument",
    "SupportTicketSource",
    "SupportTicketStatus",
]
