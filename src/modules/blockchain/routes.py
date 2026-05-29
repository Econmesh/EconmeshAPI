"""Routes for ``blockchain``. SKELETON."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.blockchain.controller import BlockchainController
from src.modules.blockchain.repository import BlockchainRepository
from src.modules.blockchain.service import BlockchainService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.pagination import PaginationParams

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/blockchain", tags=["blockchain"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> BlockchainController:
    repo = BlockchainRepository(db)
    service = BlockchainService(repo)
    return BlockchainController(service)


ControllerDep = Annotated[BlockchainController, Depends(_build_controller)]


@router.get(
    "/anchors",
    summary="List blockchain anchors (TODO).",
    status_code=status.HTTP_200_OK,
)
async def list_anchors(
    controller: ControllerDep,
    _user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
):
    # TODO: implement
    return await controller.list(pagination.page, pagination.page_size)


__all__ = ["router"]
