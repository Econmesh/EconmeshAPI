"""Public (unauthenticated) support routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.support.controller import PublicSupportController
from src.modules.support.deps import build_public_support_controller
from src.modules.support.schema import (
    ExternalSupportContactCreate,
    PublicContactRequestCreate,
)
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/public/support", tags=["public-support"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> PublicSupportController:
    return build_public_support_controller(db, redis_client)


ControllerDep = Annotated[PublicSupportController, Depends(_build_controller)]


@router.post(
    "/contact",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a contact request from the public website chat widget.",
)
async def submit_contact(
    payload: ExternalSupportContactCreate,
    controller: ControllerDep,
) -> MessageResponse:
    return await controller.submit_contact(payload)


@router.post(
    "/contact-request",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a DMC/MRI contact request from the public website.",
)
async def submit_contact_request(
    payload: PublicContactRequestCreate,
    controller: ControllerDep,
) -> MessageResponse:
    return await controller.submit_contact_request(payload)


__all__ = ["router"]
