"""Administrator routes for DMC agents, queue and assignment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.modules.dmc.admin_service import DmcAdminService
from src.modules.dmc.deps import build_admin_service
from src.modules.dmc.schema import (
    AuditEventListResponse,
    DmcAgentDetailResponse,
    DmcAssignmentModeUpdate,
    DmcAvailabilityUpdate,
    DmcCompanyDetail,
    DmcPortfolioLinkCreate,
    DmcQueueAgent,
    DmcQueueReorder,
    DmcQueueResponse,
    DmcTicketAssign,
    DmcTicketListResponse,
)
from src.shared.constants.permissions import Permission
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_permission, require_role
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(
    prefix="/admin/dmc",
    tags=["admin-dmc"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


def _build_service(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> DmcAdminService:
    return build_admin_service(db, redis_client)


ServiceDep = Annotated[DmcAdminService, Depends(_build_service)]


@router.get(
    "/queue",
    response_model=DmcQueueResponse,
    dependencies=[Depends(require_permission(Permission.DMC_QUEUE_CONFIGURE))],
)
async def get_queue(service: ServiceDep) -> DmcQueueResponse:
    return await service.queue()


@router.patch(
    "/settings",
    response_model=DmcQueueResponse,
    dependencies=[Depends(require_permission(Permission.DMC_QUEUE_CONFIGURE))],
)
async def update_assignment_mode(
    payload: DmcAssignmentModeUpdate,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcQueueResponse:
    return await service.set_mode(payload.mode, actor_firebase_uid=current_user.uid)


@router.put(
    "/queue",
    response_model=DmcQueueResponse,
    dependencies=[Depends(require_permission(Permission.DMC_QUEUE_CONFIGURE))],
)
async def reorder_queue(
    payload: DmcQueueReorder,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcQueueResponse:
    return await service.reorder(payload.agent_user_ids, actor_firebase_uid=current_user.uid)


@router.get(
    "/agents/{agent_user_id}",
    response_model=DmcAgentDetailResponse,
    dependencies=[Depends(require_permission(Permission.DMC_AGENTS_MANAGE))],
)
async def get_agent(agent_user_id: UUID, service: ServiceDep) -> DmcAgentDetailResponse:
    return await service.get_agent(agent_user_id)


@router.patch(
    "/agents/{agent_user_id}/availability",
    response_model=DmcQueueAgent,
    dependencies=[Depends(require_permission(Permission.DMC_AGENTS_MANAGE))],
)
async def set_availability(
    agent_user_id: UUID,
    payload: DmcAvailabilityUpdate,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcQueueAgent:
    return await service.set_availability(
        agent_user_id,
        available=payload.available,
        actor_firebase_uid=current_user.uid,
    )


@router.post(
    "/agents/{agent_user_id}/companies",
    response_model=DmcCompanyDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.DMC_AGENTS_MANAGE))],
)
async def link_company(
    agent_user_id: UUID,
    payload: DmcPortfolioLinkCreate,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcCompanyDetail:
    return await service.link_company(
        agent_user_id,
        payload.company_id,
        payload.source,
        actor_firebase_uid=current_user.uid,
    )


@router.delete(
    "/agents/{agent_user_id}/companies/{company_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission(Permission.DMC_AGENTS_MANAGE))],
)
async def unlink_company(
    agent_user_id: UUID,
    company_id: UUID,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> MessageResponse:
    await service.unlink_company(
        agent_user_id, company_id, actor_firebase_uid=current_user.uid
    )
    return MessageResponse(message="Empresa desvinculada.")


@router.get(
    "/agents/{agent_user_id}/tickets",
    response_model=DmcTicketListResponse,
    dependencies=[Depends(require_permission(Permission.SUPPORT_ASSIGN))],
)
async def list_agent_tickets(
    agent_user_id: UUID,
    service: ServiceDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DmcTicketListResponse:
    return await service.list_agent_tickets(agent_user_id, page=page, page_size=page_size)


@router.post(
    "/tickets/{ticket_id}/assign",
    response_model=DmcTicketListResponse,
    dependencies=[Depends(require_permission(Permission.SUPPORT_ASSIGN))],
)
async def assign_ticket(
    ticket_id: UUID,
    payload: DmcTicketAssign,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DmcTicketListResponse:
    return await service.assign_ticket(
        ticket_id, payload.agent_user_id, actor_firebase_uid=current_user.uid
    )


@router.get(
    "/audit",
    response_model=AuditEventListResponse,
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
)
async def list_audit(
    service: ServiceDep, limit: int = Query(default=100, ge=1, le=200)
) -> AuditEventListResponse:
    return await service.audit_log(limit=limit)


__all__ = ["router"]
