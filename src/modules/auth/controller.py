"""HTTP controller for the ``auth`` module — thin orchestration layer."""

from __future__ import annotations

from src.modules.auth.schema import (
    AdminRegisterRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
)
from src.modules.auth.service import AuthService
from src.shared.dependencies.auth import CurrentUser
from src.shared.schemas.responses import MessageResponse


class AuthController:
    """HTTP entry-points; keep zero domain logic here."""

    def __init__(self, service: AuthService) -> None:
        self._service = service

    async def register(self, payload: RegisterRequest) -> RegisterResponse:
        return await self._service.register(payload)

    async def register_by_admin(self, payload: AdminRegisterRequest) -> RegisterResponse:
        return await self._service.register_by_admin(payload)

    async def verify_account(self, token: str) -> MessageResponse:
        return await self._service.verify_account(token)

    async def resend_verification(self, email: str) -> MessageResponse:
        return await self._service.resend_verification(email)

    async def login(self, payload: LoginRequest) -> LoginResponse:
        return await self._service.login_with_id_token(payload.id_token)

    async def me(self, current_user: CurrentUser) -> MeResponse:
        return await self._service.get_me(current_user.uid)

    async def logout(self, current_user: CurrentUser) -> MessageResponse:
        await self._service.logout(current_user.uid)
        return MessageResponse(message="Signed out successfully.")

    async def revoke_all(self, current_user: CurrentUser) -> MessageResponse:
        await self._service.revoke_all_sessions(current_user.uid)
        return MessageResponse(message="All sessions were revoked.")


__all__ = ["AuthController"]
