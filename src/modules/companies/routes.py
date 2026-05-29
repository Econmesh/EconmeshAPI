"""Routes for ``companies``. SKELETON — endpoints declared, bodies TODO."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.companies.controller import CompaniesController
from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.service import CompaniesService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.pagination import PaginationParams

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/companies", tags=["companies"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> CompaniesController:
    repo = CompaniesRepository(db)
    service = CompaniesService(repo)
    return CompaniesController(service)


ControllerDep = Annotated[CompaniesController, Depends(_build_controller)]


@router.get(
    "",
    summary="List companies (TODO).",
    status_code=status.HTTP_200_OK,
)
async def list_companies(
    controller: ControllerDep,
    _user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
):
    # TODO: implement listing
    return await controller.list(pagination.page, pagination.page_size)


__all__ = ["router"]
