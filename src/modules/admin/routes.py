"""Cross-tenant admin routes — all require ``role=admin``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.modules.admin.controller import AdminController
from src.modules.admin.schema import (
    AdminCompanyCreate,
    AdminCompanyListResponse,
    AdminRegisterRequest,
    AdminUserListItem,
    AdminUserListParams,
    AdminUserListResponse,
    AdminUserUpdate,
)
from src.modules.admin.service import AdminService
from src.modules.auth.repository import AuthRepository, EmailVerificationRepository
from src.modules.auth.schema import MeResponse, RegisterResponse
from src.modules.auth.service import AuthService
from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.schema import CompanyResponse, CompanyUpdate
from src.modules.companies.service import CompaniesService
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.opportunities.schema import (
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from src.modules.opportunities.service import OpportunitiesService
from src.shared.constants.roles import Role
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_role
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.pagination import PaginationParams
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> AdminController:
    auth_repo = AuthRepository(db)
    auth_service = AuthService(
        repository=auth_repo,
        redis_client=redis_client,
        verification_repository=EmailVerificationRepository(db),
    )
    companies_repo = CompaniesRepository(db)
    companies_service = CompaniesService(companies_repo, auth_repo)
    opportunities_repo = OpportunitiesRepository(db)
    opportunities_service = OpportunitiesService(
        opportunities_repo, auth_repo, companies_repo
    )
    service = AdminService(
        auth_repository=auth_repo,
        auth_service=auth_service,
        companies_repository=companies_repo,
        companies_service=companies_service,
        opportunities_repository=opportunities_repo,
        opportunities_service=opportunities_service,
    )
    return AdminController(service)


ControllerDep = Annotated[AdminController, Depends(_build_controller)]


def _user_list_params(
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
    role: Role | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    email: str | None = Query(default=None, max_length=254),
) -> AdminUserListParams:
    return AdminUserListParams(
        page=pagination.page,
        page_size=pagination.page_size,
        role=role,
        is_active=is_active,
        email=email,
    )


UserListParamsDep = Annotated[AdminUserListParams, Depends(_user_list_params)]


# --------------------------------------------------------------------- users
@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List all users.",
)
async def list_users(
    controller: ControllerDep, params: UserListParamsDep
) -> AdminUserListResponse:
    return await controller.list_users(params)


@router.get(
    "/users/{user_id}",
    response_model=AdminUserListItem,
    summary="Get a user by ID.",
)
async def get_user(controller: ControllerDep, user_id: UUID) -> AdminUserListItem:
    return await controller.get_user(user_id)


@router.post(
    "/users",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user with an arbitrary role.",
)
async def create_user(
    payload: AdminRegisterRequest, controller: ControllerDep
) -> RegisterResponse:
    return await controller.create_user(payload)


@router.patch(
    "/users/{user_id}",
    response_model=MeResponse,
    summary="Update a user (role, status, profile).",
)
async def update_user(
    user_id: UUID, payload: AdminUserUpdate, controller: ControllerDep
) -> MeResponse:
    return await controller.update_user(user_id, payload)


# ----------------------------------------------------------------- companies
@router.get(
    "/companies",
    response_model=AdminCompanyListResponse,
    summary="List all companies.",
)
async def list_companies(
    controller: ControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> AdminCompanyListResponse:
    return await controller.list_companies(
        page=pagination.page, page_size=pagination.page_size
    )


@router.get(
    "/companies/{company_id}",
    response_model=CompanyResponse,
    summary="Get a company by ID.",
)
async def get_company(
    controller: ControllerDep, company_id: UUID
) -> CompanyResponse:
    return await controller.get_company(company_id)


@router.post(
    "/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company for a specific user.",
)
async def create_company(
    payload: AdminCompanyCreate, controller: ControllerDep
) -> CompanyResponse:
    return await controller.create_company(payload)


@router.patch(
    "/companies/{company_id}",
    response_model=CompanyResponse,
    summary="Update a company.",
)
async def update_company(
    company_id: UUID, payload: CompanyUpdate, controller: ControllerDep
) -> CompanyResponse:
    return await controller.update_company(company_id, payload)


@router.delete(
    "/companies/{company_id}",
    response_model=MessageResponse,
    summary="Soft-delete a company.",
)
async def delete_company(
    controller: ControllerDep, company_id: UUID
) -> MessageResponse:
    await controller.delete_company(company_id)
    return MessageResponse(message="Company deleted successfully.")


# ------------------------------------------------------------- opportunities
@router.get(
    "/opportunities",
    response_model=OpportunityListResponse,
    summary="List all opportunities.",
)
async def list_opportunities(
    controller: ControllerDep,
    params: Annotated[OpportunityListParams, Depends(OpportunityListParams.as_query)],
) -> OpportunityListResponse:
    return await controller.list_opportunities(params)


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Get an opportunity by ID.",
)
async def get_opportunity(
    controller: ControllerDep, opportunity_id: UUID
) -> OpportunityResponse:
    return await controller.get_opportunity(opportunity_id)


@router.patch(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Update an opportunity.",
)
async def update_opportunity(
    opportunity_id: UUID,
    payload: OpportunityUpdate,
    controller: ControllerDep,
) -> OpportunityResponse:
    return await controller.update_opportunity(opportunity_id, payload)


@router.delete(
    "/opportunities/{opportunity_id}",
    response_model=MessageResponse,
    summary="Soft-delete an opportunity.",
)
async def delete_opportunity(
    controller: ControllerDep, opportunity_id: UUID
) -> MessageResponse:
    await controller.delete_opportunity(opportunity_id)
    return MessageResponse(message="Opportunity deleted successfully.")


__all__ = ["router"]
