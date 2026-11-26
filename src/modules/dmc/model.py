"""Persistence models for the DMC agent portfolio, queue and direct channel."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument


class PortfolioSource(StrEnum):
    REGISTERED = "registered"
    ASSIGNED = "assigned"


class DmcConversationAuthorRole(StrEnum):
    DMC_AGENT = "dmc_agent"
    USER = "user"


class AuditAction(StrEnum):
    AGENT_CREATED = "dmc_agent.created"
    AGENT_ACTIVATED = "dmc_agent.activated"
    AGENT_DEACTIVATED = "dmc_agent.deactivated"
    AGENT_AVAILABILITY_CHANGED = "dmc_agent.availability_changed"
    AGENT_ROLE_CHANGED = "dmc_agent.role_changed"
    PORTFOLIO_LINKED = "dmc_portfolio.linked"
    PORTFOLIO_UNLINKED = "dmc_portfolio.unlinked"
    TICKET_ASSIGNED = "dmc_ticket.assigned"
    TICKET_REASSIGNED = "dmc_ticket.reassigned"
    TICKET_UNASSIGNED = "dmc_ticket.unassigned"
    TICKET_CLOSED = "dmc_ticket.closed"
    SUPPORT_REPLIED = "dmc_support.replied"
    MESSAGE_SENT = "dmc_conversation.message_sent"
    NOTIFICATION_SENT = "dmc_notification.sent"
    QUEUE_REORDERED = "dmc_queue.reordered"
    ASSIGNMENT_MODE_CHANGED = "dmc_assignment_mode.changed"
    COMPANY_PRE_REGISTERED = "company.pre_registered"
    COMPANY_PRE_REGISTRATION_UPDATED = "company.pre_registration_updated"


class DmcAgentDocument(DomainDocument):
    collection_name: ClassVar[str] = "dmc_agents"

    user_id: UUID
    available: bool = True
    queue_position: int = 0
    last_assigned_at: datetime | None = None
    created_by: UUID | None = None


class DmcPortfolioLinkDocument(DomainDocument):
    collection_name: ClassVar[str] = "dmc_portfolio"

    agent_user_id: UUID
    company_id: UUID
    source: PortfolioSource = PortfolioSource.ASSIGNED
    linked_by: UUID | None = None


class DmcConversationDocument(DomainDocument):
    collection_name: ClassVar[str] = "dmc_conversations"

    agent_user_id: UUID
    user_id: UUID
    company_id: UUID
    last_message_at: datetime | None = None
    last_author_role: DmcConversationAuthorRole | None = None
    last_message_preview: str | None = None


class DmcConversationMessageDocument(DomainDocument):
    collection_name: ClassVar[str] = "dmc_conversation_messages"

    conversation_id: UUID
    author_id: UUID
    author_role: DmcConversationAuthorRole
    body: str


class DmcNotificationBatchDocument(DomainDocument):
    collection_name: ClassVar[str] = "dmc_notification_batches"

    agent_user_id: UUID
    title: str
    body: str
    recipient_user_ids: list[UUID] = Field(default_factory=list)


class AuditEventDocument(DomainDocument):
    collection_name: ClassVar[str] = "audit_events"

    actor_user_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


__all__ = [
    "AuditAction",
    "AuditEventDocument",
    "DmcAgentDocument",
    "DmcConversationAuthorRole",
    "DmcConversationDocument",
    "DmcConversationMessageDocument",
    "DmcNotificationBatchDocument",
    "DmcPortfolioLinkDocument",
    "PortfolioSource",
]
