"""Business rules for ``users``. SKELETON — implement when wiring the routes."""

from __future__ import annotations

from uuid import UUID

from src.modules.users.repository import UsersRepository
from src.modules.users.schema import (
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)


class UsersService:
    def __init__(self, repository: UsersRepository) -> None:
        self._repo = repository

    async def list(self, *, page: int, page_size: int) -> list[UserProfileResponse]:
        raise NotImplementedError("TODO: list user profiles with pagination")

    async def get(self, profile_id: UUID) -> UserProfileResponse:
        raise NotImplementedError("TODO: fetch one profile")

    async def create(
        self, *, user_id: UUID, payload: UserProfileCreate
    ) -> UserProfileResponse:
        raise NotImplementedError("TODO: create profile for user_id")

    async def update(
        self, profile_id: UUID, payload: UserProfileUpdate
    ) -> UserProfileResponse:
        raise NotImplementedError("TODO: update profile")

    async def delete(self, profile_id: UUID) -> None:
        raise NotImplementedError("TODO: delete profile")


__all__ = ["UsersService"]
