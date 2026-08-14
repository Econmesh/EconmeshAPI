"""Routes for ``companies``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status

from src.modules.auth.repository import AuthRepository
from src.modules.companies.controller import CompaniesController
from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.schema import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    LogoPresignRequest,
    LogoPresignResponse,
)
from src.modules.companies.service import CompaniesService
from src.modules.companies.compliance_review import build_compliance_review_service
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.pagination import PaginationParams
from src.shared.schemas.responses import StorageUploadResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/companies", tags=["companies"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> CompaniesController:
    repo = CompaniesRepository(db)
    auth_repo = AuthRepository(db)
    service = CompaniesService(
        repo, auth_repo, compliance_review=build_compliance_review_service(db, redis_client)
    )
    return CompaniesController(service)


ControllerDep = Annotated[CompaniesController, Depends(_build_controller)]


@router.get(
    "",
    response_model=list[CompanyResponse],
    summary="List companies owned by the current user.",
    status_code=status.HTTP_200_OK,
)
async def list_companies(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> list[CompanyResponse]:
    return await controller.list(current_user, pagination.page, pagination.page_size)


@router.post(
    "",
    response_model=CompanyResponse,
    summary="Create a new company.",
    status_code=status.HTTP_201_CREATED,
)
async def create_company(
    payload: CompanyCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> CompanyResponse:
    return await controller.create(payload, current_user)


@router.post(
    "/logo/presign",
    response_model=LogoPresignResponse,
    summary="Request a presigned URL to upload a company logo to Firebase Storage.",
    status_code=status.HTTP_200_OK,
)
async def presign_company_logo(
    payload: LogoPresignRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> LogoPresignResponse:
    return await controller.presign_logo(payload, current_user)


@router.post(
    "/logo/upload",
    response_model=StorageUploadResponse,
    summary="Upload a company logo via the API (avoids browser CORS to Storage).",
    status_code=status.HTTP_200_OK,
)
async def upload_company_logo(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
) -> StorageUploadResponse:
    return await controller.upload_logo(file, current_user)


@router.post(
    "/{company_id}/documents/{kind}/upload",
    response_model=CompanyResponse,
    summary="Upload or replace a company compliance document (operating_license or mtr).",
    status_code=status.HTTP_200_OK,
)
async def upload_company_document(
    company_id: UUID,
    kind: str,
    controller: ControllerDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
) -> CompanyResponse:
    return await controller.upload_document(company_id, kind, file, current_user)


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Get company details.",
    status_code=status.HTTP_200_OK,
)
async def get_company(
    company_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> CompanyResponse:
    return await controller.get(company_id, current_user)


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Update a company.",
    status_code=status.HTTP_200_OK,
)
async def update_company(
    company_id: UUID,
    payload: CompanyUpdate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> CompanyResponse:
    return await controller.update(company_id, payload, current_user)


@router.delete(
    "/{company_id}",
    summary="Soft-delete a company.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_company(
    company_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> None:
    await controller.delete(company_id, current_user)


__all__ = ["router"]
