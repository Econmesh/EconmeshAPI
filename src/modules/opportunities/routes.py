"""Routes for ``opportunities``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status

from src.modules.auth.repository import AuthRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.opportunities.controller import OpportunitiesController
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.opportunities.schema import (
    OpportunityCreate,
    OpportunityImagePresignRequest,
    OpportunityImagePresignResponse,
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from src.modules.opportunities.service import OpportunitiesService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.responses import StorageUploadResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> OpportunitiesController:
    repo = OpportunitiesRepository(db)
    auth_repo = AuthRepository(db)
    companies_repo = CompaniesRepository(db)
    service = OpportunitiesService(repo, auth_repo, companies_repo)
    return OpportunitiesController(service)


ControllerDep = Annotated[OpportunitiesController, Depends(_build_controller)]


@router.get(
    "",
    response_model=OpportunityListResponse,
    summary="List marketplace opportunities.",
    status_code=status.HTTP_200_OK,
)
async def list_opportunities(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    params: Annotated[OpportunityListParams, Depends(OpportunityListParams.as_query)],
) -> OpportunityListResponse:
    return await controller.list(params, current_user)


@router.post(
    "",
    response_model=OpportunityResponse,
    summary="Create a new opportunity.",
    status_code=status.HTTP_201_CREATED,
)
async def create_opportunity(
    payload: OpportunityCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> OpportunityResponse:
    return await controller.create(payload, current_user)


@router.post(
    "/images/presign",
    response_model=OpportunityImagePresignResponse,
    summary="Request a presigned URL to upload an opportunity image.",
    status_code=status.HTTP_200_OK,
)
async def presign_opportunity_image(
    payload: OpportunityImagePresignRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> OpportunityImagePresignResponse:
    return await controller.presign_image(payload, current_user)


@router.post(
    "/images/upload",
    response_model=StorageUploadResponse,
    summary="Upload an opportunity image via the API (avoids browser CORS to Storage).",
    status_code=status.HTTP_200_OK,
)
async def upload_opportunity_image(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
) -> StorageUploadResponse:
    return await controller.upload_image(file, current_user)


@router.get(
    "/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Get opportunity details.",
    status_code=status.HTTP_200_OK,
)
async def get_opportunity(
    opportunity_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> OpportunityResponse:
    return await controller.get(opportunity_id, current_user)


@router.patch(
    "/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Update an opportunity.",
    status_code=status.HTTP_200_OK,
)
async def update_opportunity(
    opportunity_id: UUID,
    payload: OpportunityUpdate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> OpportunityResponse:
    return await controller.update(opportunity_id, payload, current_user)


@router.delete(
    "/{opportunity_id}",
    summary="Soft-delete an opportunity.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_opportunity(
    opportunity_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> None:
    await controller.delete(opportunity_id, current_user)


__all__ = ["router"]
