"""Routes for a company user talking to their DMC agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.modules.dmc.agent_service import DmcAgentService
from src.modules.dmc.deps import build_agent_service, build_portal_service
from src.modules.dmc.portal import DmcPortalService
from src.modules.dmc.schema import (
    DmcContactCreate,
    DmcConversationListResponse,
    DmcConversationMessageResponse,
    DmcMessageCreate,
    DmcMessageListResponse,
)
from src.modules.support.schema import SupportTicketResponse
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/my/dmc", tags=["my-dmc"])


def _portal(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> DmcPortalService:
    return build_portal_service(db, redis_client)


def _agent(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> DmcAgentService:
    return build_agent_service(db, redis_client)


PortalDep = Annotated[DmcPortalService, Depends(_portal)]
AgentDep = Annotated[DmcAgentService, Depends(_agent)]


@router.post(
    "/contact",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request contact with a DMC agent.",
)
async def request_dmc_contact(
    payload: DmcContactCreate,
    portal: PortalDep,
    current_user: CurrentUserDep,
) -> SupportTicketResponse:
    return await portal.request_contact(current_user.uid, payload.message)


@router.get("/conversations", response_model=DmcConversationListResponse)
async def list_my_dmc_conversations(
    service: AgentDep, current_user: CurrentUserDep
) -> DmcConversationListResponse:
    return await service.list_user_conversations(current_user.uid)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=DmcMessageListResponse,
)
async def list_my_dmc_messages(
    conversation_id: UUID, service: AgentDep, current_user: CurrentUserDep
) -> DmcMessageListResponse:
    return await service.list_user_messages(current_user.uid, conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=DmcConversationMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reply_my_dmc_conversation(
    conversation_id: UUID,
    payload: DmcMessageCreate,
    service: AgentDep,
    current_user: CurrentUserDep,
) -> DmcConversationMessageResponse:
    return await service.reply_as_user(current_user.uid, conversation_id, payload.body)


__all__ = ["router"]
