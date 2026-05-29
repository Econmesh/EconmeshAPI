"""HTTP controller for ``users``. SKELETON — thin glue over the service."""

from __future__ import annotations

from uuid import UUID

from src.modules.users.schema import (
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)
from src.modules.users.service import UsersService


class UsersController:
    def __init__(self, service: UsersService) -> None:
        self._service = service

    async def list(self, page: int, page_size: int) -> list[UserProfileResponse]:
        return await self._service.list(page=page, page_size=page_size)

    async def get(self, profile_id: UUID) -> UserProfileResponse:
        return await self._service.get(profile_id)

    async def create(
        self, user_id: UUID, payload: UserProfileCreate
    ) -> UserProfileResponse:
        return await self._service.create(user_id=user_id, payload=payload)

    async def update(
        self, profile_id: UUID, payload: UserProfileUpdate
    ) -> UserProfileResponse:
        return await self._service.update(profile_id, payload)

    async def delete(self, profile_id: UUID) -> None:
        await self._service.delete(profile_id)


__all__ = ["UsersController"]
