"""HTTP DTOs for the DMC agent area."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.companies.model import CompanyRegistrationStatus
from src.modules.companies.schema import CompanyAddressResponse
from src.modules.dmc.model import DmcConversationAuthorRole, PortfolioSource
from src.modules.platform_settings.model import DmcAssignmentMode
from src.modules.support.model import SupportTicketStatus
from src.shared.schemas.base import APIModel


class DmcIndicator(APIModel):
    key: str
    label: str
    value: int


class DmcTicketSummary(APIModel):
    id: UUID
    ticket_number: int
    subject: str
    status: SupportTicketStatus
    company: str | None = None
    visitor_name: str | None = None
    visitor_email: str | None = None
    phone: str | None = None
    position: str | None = None
    user_id: UUID | None = None
    company_id: UUID | None = None
    assigned_agent_id: UUID | None = None
    last_message_at: datetime | None = None
    created_at: datetime


class DmcDashboardResponse(APIModel):
    indicators: list[DmcIndicator]
    recent_tickets: list[DmcTicketSummary]


class DmcCompanyPublic(APIModel):
    id: UUID
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    city: str | None = None
    state: str | None = None
    sector: str | None = None
    in_portfolio: bool
    registration_status: CompanyRegistrationStatus = CompanyRegistrationStatus.COMPLETE


class DmcCompanyDetail(DmcCompanyPublic):
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    description: str | None = None
    legal_representative: str | None = None
    address: CompanyAddressResponse | None = None
    source: PortfolioSource | None = None
    owner_user_id: UUID | None = None
    owner_name: str | None = None


class DmcCompanyUser(APIModel):
    id: UUID
    name: str | None = None
    email: str | None = None
    job_title: str | None = None
    company_id: UUID


class DmcCompanyListResponse(APIModel):
    items: list[DmcCompanyDetail]
    total: int


class DmcCompanySearchResponse(APIModel):
    items: list[DmcCompanyPublic]
    total: int


class DmcConversationCreate(APIModel):
    user_id: UUID
    body: str = Field(..., min_length=1, max_length=5000)


class DmcMessageCreate(APIModel):
    body: str = Field(..., min_length=1, max_length=5000)


class DmcConversationMessageResponse(APIModel):
    id: UUID
    conversation_id: UUID
    author_id: UUID
    author_role: DmcConversationAuthorRole
    author_name: str | None = None
    body: str
    created_at: datetime


class DmcConversationResponse(APIModel):
    id: UUID
    agent_user_id: UUID
    user_id: UUID
    user_name: str | None = None
    company_id: UUID
    company_name: str | None = None
    last_message_at: datetime | None = None
    last_author_role: DmcConversationAuthorRole | None = None
    last_message_preview: str | None = None
    created_at: datetime


class DmcConversationListResponse(APIModel):
    items: list[DmcConversationResponse]
    total: int


class DmcMessageListResponse(APIModel):
    items: list[DmcConversationMessageResponse]
    total: int


class DmcNotificationSend(APIModel):
    title: str = Field(..., min_length=1, max_length=160)
    body: str = Field(..., min_length=1, max_length=4000)
    user_ids: list[UUID] = Field(..., min_length=1, max_length=100)


class DmcNotificationBatchResponse(APIModel):
    id: UUID
    title: str
    body: str
    recipient_user_ids: list[UUID]
    created_at: datetime


class DmcNotificationHistoryResponse(APIModel):
    items: list[DmcNotificationBatchResponse]
    total: int


class DmcTicketListResponse(APIModel):
    items: list[DmcTicketSummary]
    total: int
    page: int
    page_size: int


class DmcSupportReply(APIModel):
    body: str = Field(..., min_length=1, max_length=5000)


class DmcQueueAgent(APIModel):
    user_id: UUID
    name: str | None = None
    email: str | None = None
    is_active: bool
    available: bool
    queue_position: int
    open_count: int = 0
    in_progress_count: int = 0
    last_assigned_at: datetime | None = None


class DmcQueueResponse(APIModel):
    mode: DmcAssignmentMode
    next_agent_user_id: UUID | None = None
    agents: list[DmcQueueAgent]


class DmcAssignmentModeUpdate(APIModel):
    mode: DmcAssignmentMode


class DmcQueueReorder(APIModel):
    agent_user_ids: list[UUID] = Field(..., min_length=1)


class DmcAvailabilityUpdate(APIModel):
    available: bool


class DmcPortfolioLinkCreate(APIModel):
    company_id: UUID
    source: PortfolioSource = PortfolioSource.ASSIGNED


class DmcTicketAssign(APIModel):
    agent_user_id: UUID


class AuditEventResponse(APIModel):
    id: UUID
    actor_user_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    created_at: datetime


class AuditEventListResponse(APIModel):
    items: list[AuditEventResponse]
    total: int


class DmcAgentDetailResponse(APIModel):
    user_id: UUID
    name: str | None = None
    email: str | None = None
    is_active: bool
    available: bool
    queue_position: int
    companies: list[DmcCompanyDetail]
    open_count: int
    in_progress_count: int
    last_assigned_at: datetime | None = None


class DmcContactCreate(APIModel):
    message: str = Field(..., min_length=1, max_length=4000)


__all__ = [
    "AuditEventListResponse",
    "AuditEventResponse",
    "DmcAgentDetailResponse",
    "DmcAssignmentModeUpdate",
    "DmcAvailabilityUpdate",
    "DmcCompanyDetail",
    "DmcCompanyListResponse",
    "DmcCompanyPublic",
    "DmcCompanySearchResponse",
    "DmcCompanyUser",
    "DmcContactCreate",
    "DmcConversationCreate",
    "DmcConversationListResponse",
    "DmcConversationMessageResponse",
    "DmcConversationResponse",
    "DmcDashboardResponse",
    "DmcIndicator",
    "DmcMessageCreate",
    "DmcMessageListResponse",
    "DmcNotificationBatchResponse",
    "DmcNotificationHistoryResponse",
    "DmcNotificationSend",
    "DmcPortfolioLinkCreate",
    "DmcQueueAgent",
    "DmcQueueReorder",
    "DmcQueueResponse",
    "DmcSupportReply",
    "DmcTicketAssign",
    "DmcTicketListResponse",
    "DmcTicketSummary",
]
