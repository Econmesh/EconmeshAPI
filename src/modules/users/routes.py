"""Routes for ``users``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from src.modules.auth.repository import AuthRepository
from src.modules.users.controller import UsersController
from src.modules.users.repository import UsersRepository
from src.modules.users.schema import (
    AvatarPresignRequest,
    AvatarPresignResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from src.modules.users.service import UsersService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.responses import StorageUploadResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/users", tags=["users"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> UsersController:
    repo = UsersRepository(db)
    auth_repo = AuthRepository(db)
    service = UsersService(repo, auth_repo)
    return UsersController(service)


ControllerDep = Annotated[UsersController, Depends(_build_controller)]


@router.get(
    "/me/profile",
    response_model=UserProfileResponse,
    summary="Get the current user's extended profile.",
    status_code=status.HTTP_200_OK,
)
async def get_my_profile(
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> UserProfileResponse:
    return await controller.get_my_profile(current_user)


@router.patch(
    "/me/profile",
    response_model=UserProfileResponse,
    summary="Update the current user's profile.",
    status_code=status.HTTP_200_OK,
)
async def update_my_profile(
    payload: UserProfileUpdate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> UserProfileResponse:
    return await controller.update_my_profile(payload, current_user)


@router.post(
    "/avatar/presign",
    response_model=AvatarPresignResponse,
    summary="Request a presigned URL to upload a profile photo.",
    status_code=status.HTTP_200_OK,
)
async def presign_avatar(
    payload: AvatarPresignRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AvatarPresignResponse:
    return await controller.presign_avatar(payload, current_user)


@router.post(
    "/avatar/upload",
    response_model=StorageUploadResponse,
    summary="Upload a profile photo via the API (avoids browser CORS to Storage).",
    status_code=status.HTTP_200_OK,
)
async def upload_avatar(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
) -> StorageUploadResponse:
    return await controller.upload_avatar(file, current_user)


__all__ = ["router"]
