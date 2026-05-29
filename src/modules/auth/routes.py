"""Routes for the ``auth`` module."""

from __future__ import annotations

from typing import Annotated, TYPE_CHECKING

from fastapi import APIRouter, Depends, status

from src.modules.auth.controller import AuthController
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schema import LoginRequest, LoginResponse, MeResponse
from src.modules.auth.service import AuthService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> AuthController:
    repository = AuthRepository(db)
    service = AuthService(repository=repository, redis_client=redis_client)
    return AuthController(service)


ControllerDep = Annotated[AuthController, Depends(_build_controller)]


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify a Firebase ID token and create/refresh the user record.",
)
async def login(payload: LoginRequest, controller: ControllerDep) -> LoginResponse:
    return await controller.login(payload)


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
