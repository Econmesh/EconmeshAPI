"""Routes for the ``coming_soon`` module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.coming_soon.controller import ComingSoonController
from src.modules.coming_soon.repository import ComingSoonRepository
from src.modules.coming_soon.schema import ComingSoonSubscribeRequest
from src.modules.coming_soon.service import ComingSoonService
from src.shared.dependencies.db import get_db
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/coming-soon", tags=["coming-soon"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> ComingSoonController:
    repository = ComingSoonRepository(db)
    service = ComingSoonService(repository)
    return ComingSoonController(service)


ControllerDep = Annotated[ComingSoonController, Depends(_build_controller)]


@router.post(
    "/subscribe",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an email for coming-soon launch notifications.",
)
async def subscribe(
    payload: ComingSoonSubscribeRequest,
    controller: ControllerDep,
) -> MessageResponse:
    return await controller.subscribe(payload)


__all__ = ["router"]
