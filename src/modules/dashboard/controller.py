"""HTTP adapters for dashboard endpoints."""

from __future__ import annotations

from src.modules.dashboard.schema import AdminDashboardResponse, UserDashboardResponse
from src.modules.dashboard.service import DashboardService
from src.shared.dependencies.auth import CurrentUser


class DashboardController:
    def __init__(self, service: DashboardService) -> None:
        self._service = service

    async def admin(self, days: int) -> AdminDashboardResponse:
        return await self._service.get_admin_dashboard(days=days)

    async def me(self, current_user: CurrentUser, days: int) -> UserDashboardResponse:
        return await self._service.get_user_dashboard(
            firebase_uid=current_user.uid,
            days=days,
        )


__all__ = ["DashboardController"]
