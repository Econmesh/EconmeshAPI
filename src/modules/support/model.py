"""Persistence models for support tickets."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument


class SupportTicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class SupportAuthorRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class SupportMessageType(StrEnum):
    USER_MESSAGE = "user_message"
    ADMIN_REPLY = "admin_reply"
    INTERNAL_NOTE = "internal_note"


class SupportTicketDocument(DomainDocument):
    collection_name: ClassVar[str] = "support_tickets"

    user_id: UUID
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
    "SupportAuthorRole",
    "SupportMessageDocument",
    "SupportMessageType",
    "SupportTicketDocument",
    "SupportTicketStatus",
]
