"""HTTP controller for ``users``."""

from __future__ import annotations

from src.modules.users.schema import (
    AvatarPresignRequest,
    AvatarPresignResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from src.modules.users.service import UsersService
from src.shared.dependencies.auth import CurrentUser


class UsersController:
    def __init__(self, service: UsersService) -> None:
        self._service = service

    async def get_my_profile(self, current_user: CurrentUser) -> UserProfileResponse:
        return await self._service.get_my_profile(firebase_uid=current_user.uid)

    async def update_my_profile(
        self, payload: UserProfileUpdate, current_user: CurrentUser
    ) -> UserProfileResponse:
        return await self._service.update_my_profile(
            payload, firebase_uid=current_user.uid
        )

    async def presign_avatar(
        self, payload: AvatarPresignRequest, current_user: CurrentUser
    ) -> AvatarPresignResponse:
        return await self._service.presign_avatar(
            payload, firebase_uid=current_user.uid
        )


__all__ = ["UsersController"]
