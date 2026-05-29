"""Routes for ``files``. SKELETON."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.files.controller import FilesController
from src.modules.files.repository import FilesRepository
from src.modules.files.service import FilesService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.pagination import PaginationParams

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/files", tags=["files"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> FilesController:
    repo = FilesRepository(db)
    service = FilesService(repo)
    return FilesController(service)


ControllerDep = Annotated[FilesController, Depends(_build_controller)]


@router.get(
    "",
    summary="List files owned by the current user (TODO).",
    status_code=status.HTTP_200_OK,
)
async def list_files(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
):
    # TODO: implement
    from uuid import UUID

    owner_id = UUID(int=0)  # placeholder; real impl will translate firebase_uid -> user_id
    _ = current_user
    return await controller.list_for_owner(owner_id, pagination.page, pagination.page_size)


__all__ = ["router"]
