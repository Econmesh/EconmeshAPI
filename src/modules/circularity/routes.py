"""Routes for ``circularity``. SKELETON."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.modules.circularity.controller import CircularityController
from src.modules.circularity.repository import CircularityRepository
from src.modules.circularity.service import CircularityService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.pagination import PaginationParams

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/circularity", tags=["circularity"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> CircularityController:
    repo = CircularityRepository(db)
    service = CircularityService(repo)
    return CircularityController(service)


ControllerDep = Annotated[CircularityController, Depends(_build_controller)]


@router.get(
    "/companies/{company_id}/flows",
    summary="List material flows for a company (TODO).",
    status_code=status.HTTP_200_OK,
)
async def list_company_flows(
    company_id: UUID,
    controller: ControllerDep,
    _user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
):
    # TODO: implement
    return await controller.list_for_company(
        company_id, pagination.page, pagination.page_size
    )


__all__ = ["router"]
