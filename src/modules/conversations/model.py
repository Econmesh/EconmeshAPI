"""Persistence models for opportunity conversations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from src.shared.schemas.base import DomainDocument


class ConversationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ConversationAuthorRole(StrEnum):
    OFFERER = "offerer"
    INTERESTED = "interested"
    ADMIN = "admin"
    SYSTEM = "system"


class ConversationMessageType(StrEnum):
    PARTICIPANT_MESSAGE = "participant_message"
    INTERNAL_NOTE = "internal_note"
    SYSTEM_EVENT = "system_event"


class ConversationSystemEventKind(StrEnum):
    CONTACT_CLOSED = "contact_closed"
    REOPEN_REQUESTED = "reopen_requested"
    REOPEN_REJECTED = "reopen_rejected"
    CONTACT_REOPENED = "contact_reopened"
    NEW_CONTACT_REQUESTED = "new_contact_requested"
    NEW_CONTACT_ACCEPTED = "new_contact_accepted"
    NEW_CONTACT_REJECTED = "new_contact_rejected"
    AGREEMENT_PROPOSED = "agreement_proposed"
    AGREEMENT_SUBMITTED = "agreement_submitted"
    AGREEMENT_CHANGES_REQUESTED = "agreement_changes_requested"
    AGREEMENT_REJECTED = "agreement_rejected"
    AGREEMENT_APPROVED = "agreement_approved"


class OpportunityConversationDocument(DomainDocument):
    collection_name: ClassVar[str] = "opportunity_conversations"

    opportunity_id: UUID
    opportunity_title: str
    offerer_company_id: UUID
    offerer_company_name: str
    offerer_user_id: UUID
    interested_company_id: UUID
    interested_company_name: str
    interested_user_id: UUID
    created_by_user_id: UUID
    status: ConversationStatus = ConversationStatus.OPEN
    last_message_at: datetime | None = None

    closed_by_user_id: UUID | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None

    reopen_requested_by_user_id: UUID | None = None
    reopen_requested_at: datetime | None = None
    reopen_request_message: str | None = None

    new_contact_requested_by_user_id: UUID | None = None
    new_contact_requested_at: datetime | None = None
    new_contact_request_message: str | None = None

    is_active: bool = True
    replaced_by_conversation_id: UUID | None = None
    supersedes_conversation_id: UUID | None = None


class OpportunityConversationMessageDocument(DomainDocument):
    collection_name: ClassVar[str] = "opportunity_conversation_messages"

    conversation_id: UUID
    author_id: UUID
    author_company_id: UUID | None = None
    author_role: ConversationAuthorRole
    message_type: ConversationMessageType
    body: str
    read_at: datetime | None = None
    event_kind: ConversationSystemEventKind | None = None
    event_actor_user_id: UUID | None = None
    event_actor_name: str | None = None
    event_reason: str | None = None


__all__ = [
    "ConversationAuthorRole",
    "ConversationMessageType",
    "ConversationStatus",
    "ConversationSystemEventKind",
    "OpportunityConversationDocument",
    "OpportunityConversationMessageDocument",
]
