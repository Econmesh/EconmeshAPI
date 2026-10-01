"""Routes available to a DMC agent. Administrators use /admin/dmc instead."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.modules.dmc.agent_service import DmcAgentService
from src.modules.dmc.deps import build_agent_service
from src.modules.dmc.schema import (
    DmcCompanyDetail,
    DmcCompanyListResponse,
    DmcCompanySearchResponse,
    DmcCompanyUser,
    DmcConversationCreate,
    DmcConversationListResponse,
    DmcConversationMessageResponse,
    DmcConversationResponse,
    DmcDashboardResponse,
    DmcMessageCreate,
    DmcMessageListResponse,
    DmcNotificationHistoryResponse,
    DmcNotificationSend,
    DmcNotificationBatchResponse,
    DmcSupportReply,
    DmcTicketListResponse,
    DmcTicketSummary,
)
from src.modules.opportunities.schema import (
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityResponse,
)
from src.modules.support.model import SupportTicketStatus
from src.modules.support.schema import SupportMessageResponse
from src.shared.constants.permissions import Permission
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_permission, require_role
from src.shared.dependencies.redis import get_redis

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(
    prefix="/dmc",
    tags=["dmc"],
    dependencies=[Depends(require_role(Role.DMC_AGENT))],
)


def _build_service(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> DmcAgentService:
    return build_agent_service(db, redis_client)


ServiceDep = Annotated[DmcAgentService, Depends(_build_service)]


@router.get(
    "/dashboard",
    response_model=DmcDashboardResponse,
    dependencies=[Depends(require_permission(Permission.DASHBOARD_DMC))],
)
async def dmc_dashboard(
    service: ServiceDep, current_user: CurrentUserDep
) -> DmcDashboardResponse:
    return await service.dashboard(current_user.uid)


@router.get(
    "/companies",
    response_model=DmcCompanyListResponse,
    dependencies=[Depends(require_permission(Permission.COMPANIES_READ))],
)
async def list_portfolio_companies(
    service: ServiceDep, current_user: CurrentUserDep
) -> DmcCompanyListResponse:
    return await service.list_companies(current_user.uid)


@router.get(
    "/companies/search",
    response_model=DmcCompanySearchResponse,
    dependencies=[Depends(require_permission(Permission.COMPANIES_SEARCH))],
)
async def search_companies(
    service: ServiceDep,
    current_user: CurrentUserDep,
    q: str = Query(default="", max_length=200),
) -> DmcCompanySearchResponse:
    return await service.search_companies(current_user.uid, q)


@router.get(
    "/companies/{company_id}",
    response_model=DmcCompanyDetail,
    dependencies=[Depends(require_permission(Permission.COMPANIES_READ))],
)
async def get_company(
    company_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> DmcCompanyDetail:
    return await service.get_company(current_user.uid, company_id)


@router.get(
    "/companies/{company_id}/users",
    response_model=list[DmcCompanyUser],
    dependencies=[Depends(require_permission(Permission.COMPANIES_READ))],
)
async def list_company_users(
    company_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> list[DmcCompanyUser]:
    return await service.list_company_users(current_user.uid, company_id)


@router.get(
    "/opportunities",
    response_model=OpportunityListResponse,
    dependencies=[Depends(require_permission(Permission.OPPORTUNITIES_READ))],
)
async def list_opportunities(
    service: ServiceDep,
    current_user: CurrentUserDep,
    params: Annotated[OpportunityListParams, Depends(OpportunityListParams.as_query)],
) -> OpportunityListResponse:
    return await service.list_opportunities(current_user.uid, params)


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
    dependencies=[Depends(require_permission(Permission.OPPORTUNITIES_READ))],
)
async def get_opportunity(
    opportunity_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> OpportunityResponse:
    return await service.get_opportunity(current_user.uid, opportunity_id)


@router.get(
    "/conversations",
    response_model=DmcConversationListResponse,
    dependencies=[Depends(require_permission(Permission.DMC_CONVERSATIONS_READ))],
)
async def list_conversations(
    service: ServiceDep, current_user: CurrentUserDep
) -> DmcConversationListResponse:
    return await service.list_conversations(current_user.uid)


@router.post(
    "/conversations",
    response_model=DmcConversationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.DMC_CONVERSATIONS_SEND))],
)
async def open_conversation(
    payload: DmcConversationCreate,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcConversationResponse:
    return await service.open_conversation(
        current_user.uid, user_id=payload.user_id, body=payload.body
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=DmcMessageListResponse,
    dependencies=[Depends(require_permission(Permission.DMC_CONVERSATIONS_READ))],
)
async def list_conversation_messages(
    conversation_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> DmcMessageListResponse:
    return await service.list_messages(current_user.uid, conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=DmcConversationMessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.DMC_CONVERSATIONS_SEND))],
)
async def send_conversation_message(
    conversation_id: UUID,
    payload: DmcMessageCreate,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcConversationMessageResponse:
    return await service.send_message(current_user.uid, conversation_id, payload.body)


@router.post(
    "/notifications",
    response_model=DmcNotificationBatchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.NOTIFICATIONS_SEND))],
)
async def send_notification(
    payload: DmcNotificationSend,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcNotificationBatchResponse:
    return await service.send_notification(
        current_user.uid,
        title=payload.title,
        body=payload.body,
        user_ids=payload.user_ids,
    )


@router.get(
    "/notifications/sent",
    response_model=DmcNotificationHistoryResponse,
    dependencies=[Depends(require_permission(Permission.NOTIFICATIONS_READ))],
)
async def notification_history(
    service: ServiceDep, current_user: CurrentUserDep
) -> DmcNotificationHistoryResponse:
    return await service.notification_history(current_user.uid)


@router.get(
    "/support/tickets",
    response_model=DmcTicketListResponse,
    dependencies=[Depends(require_permission(Permission.SUPPORT_DMC_READ))],
)
async def list_support_tickets(
    service: ServiceDep,
    current_user: CurrentUserDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: SupportTicketStatus | None = Query(default=None, alias="status"),
) -> DmcTicketListResponse:
    return await service.list_tickets(
        current_user.uid, page=page, page_size=page_size, status=status_filter
    )


@router.get(
    "/support/tickets/{ticket_id}",
    response_model=DmcTicketSummary,
    dependencies=[Depends(require_permission(Permission.SUPPORT_DMC_READ))],
)
async def get_support_ticket(
    ticket_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> DmcTicketSummary:
    return await service.get_ticket(current_user.uid, ticket_id)


@router.get(
    "/support/tickets/{ticket_id}/messages",
    response_model=list[SupportMessageResponse],
    dependencies=[Depends(require_permission(Permission.SUPPORT_DMC_READ))],
)
async def list_support_messages(
    ticket_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> list[SupportMessageResponse]:
    return await service.list_ticket_messages(current_user.uid, ticket_id)


@router.post(
    "/support/tickets/{ticket_id}/messages",
    response_model=SupportMessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.SUPPORT_DMC_RESPOND))],
)
async def reply_support_ticket(
    ticket_id: UUID,
    payload: DmcSupportReply,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> SupportMessageResponse:
    return await service.reply_ticket(current_user.uid, ticket_id, payload.body)


@router.post(
    "/support/tickets/{ticket_id}/close",
    response_model=DmcTicketSummary,
    dependencies=[Depends(require_permission(Permission.SUPPORT_DMC_RESPOND))],
)
async def close_support_ticket(
    ticket_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> DmcTicketSummary:
    return await service.close_ticket(current_user.uid, ticket_id)


__all__ = ["router"]
