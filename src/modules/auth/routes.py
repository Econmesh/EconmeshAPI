"""Routes for the ``auth`` module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from src.modules.auth.controller import AuthController
from src.modules.auth.repository import AuthRepository, EmailVerificationRepository
from src.modules.auth.schema import (
    AdminRegisterRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    VerifyAccountRequest,
)
from src.modules.auth.service import AuthService
from src.modules.companies.compliance_review import build_compliance_review_service
from src.modules.companies.repository import CompaniesRepository
from src.modules.users.repository import UsersRepository
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_role
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.responses import MessageResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_controller(
    db: Annotated[AsyncDatabase, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> AuthController:
    repository = AuthRepository(db)
    verification_repository = EmailVerificationRepository(db)
    service = AuthService(
        repository=repository,
        redis_client=redis_client,
        verification_repository=verification_repository,
        companies_repository=CompaniesRepository(db),
        users_repository=UsersRepository(db),
        compliance_review=build_compliance_review_service(db, redis_client),
    )
    return AuthController(service)


ControllerDep = Annotated[AuthController, Depends(_build_controller)]


def _optional_upload(file: UploadFile | None) -> UploadFile | None:
    if file is None or not (file.filename or "").strip():
        return None
    return file


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a standard user with company data and compliance documents.",
)
async def register(
    controller: ControllerDep,
    payload: Annotated[str, Form()],
    operating_license: Annotated[UploadFile, File()],
    mtr: Annotated[UploadFile | None, File()] = None,
) -> RegisterResponse:
    try:
        body = RegisterRequest.model_validate_json(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return await controller.register(
        body, operating_license=operating_license, mtr=_optional_upload(mtr)
    )


@router.post(
    "/admin/users",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user with an arbitrary role (admins only).",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def register_by_admin(
    payload: AdminRegisterRequest, controller: ControllerDep
) -> RegisterResponse:
    return await controller.register_by_admin(payload)


@router.post(
    "/verify",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm an account using the token sent by email.",
)
async def verify_account(
    payload: VerifyAccountRequest, controller: ControllerDep
) -> MessageResponse:
    return await controller.verify_account(payload.token)


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Re-send the account-confirmation email.",
)
async def resend_verification(
    payload: ResendVerificationRequest, controller: ControllerDep
) -> MessageResponse:
    return await controller.resend_verification(payload.email)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify a Firebase ID token and create/refresh the user record.",
)
async def login(payload: LoginRequest, controller: ControllerDep) -> LoginResponse:
    return await controller.login(payload)


@router.post(
    "/admin/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin-panel login — requires role=admin.",
)
async def admin_login(payload: LoginRequest, controller: ControllerDep) -> LoginResponse:
    return await controller.admin_login(payload)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Return the currently authenticated user.",
)
async def me(controller: ControllerDep, current_user: CurrentUserDep) -> MeResponse:
    return await controller.me(current_user)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Invalidate the current cached session.",
)
async def logout(
    controller: ControllerDep, current_user: CurrentUserDep
) -> MessageResponse:
    return await controller.logout(current_user)


@router.post(
    "/revoke-all",
    response_model=MessageResponse,
    summary="Revoke ALL Firebase refresh tokens for the current user (logout-everywhere).",
)
async def revoke_all(
    controller: ControllerDep, current_user: CurrentUserDep
) -> MessageResponse:
    return await controller.revoke_all(current_user)


__all__ = ["router"]
