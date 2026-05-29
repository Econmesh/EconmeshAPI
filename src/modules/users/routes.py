"""Routes for ``users``. SKELETON — endpoints declared, bodies pending implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.users.controller import UsersController
from src.modules.users.repository import UsersRepository
from src.modules.users.service import UsersService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.pagination import PaginationParams

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/users", tags=["users"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> UsersController:
    repo = UsersRepository(db)
    service = UsersService(repo)
    return UsersController(service)


ControllerDep = Annotated[UsersController, Depends(_build_controller)]


@router.get(
    "",
    summary="List user profiles (TODO).",
    status_code=status.HTTP_200_OK,
)
async def list_profiles(
    controller: ControllerDep,
    _user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
):
    # TODO: implement listing with pagination
    return await controller.list(pagination.page, pagination.page_size)


__all__ = ["router"]
