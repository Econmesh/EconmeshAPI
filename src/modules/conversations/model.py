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


class ConversationMessageType(StrEnum):
    PARTICIPANT_MESSAGE = "participant_message"
    INTERNAL_NOTE = "internal_note"


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


class OpportunityConversationMessageDocument(DomainDocument):
    collection_name: ClassVar[str] = "opportunity_conversation_messages"

    conversation_id: UUID
    author_id: UUID
    author_company_id: UUID | None = None
    author_role: ConversationAuthorRole
    message_type: ConversationMessageType
    body: str
    read_at: datetime | None = None


__all__ = [
    "ConversationAuthorRole",
    "ConversationMessageType",
    "ConversationStatus",
    "OpportunityConversationDocument",
    "OpportunityConversationMessageDocument",
]
