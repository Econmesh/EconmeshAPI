"""Dashboard routes — platform (admin) and user summaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query

from src.modules.auth.repository import AuthRepository
from src.modules.dashboard.controller import DashboardController
from src.modules.dashboard.repository import DashboardRepository
from src.modules.dashboard.schema import AdminDashboardResponse, UserDashboardResponse
from src.modules.dashboard.service import DashboardService
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_role

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(tags=["dashboard"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> DashboardController:
    repository = DashboardRepository(db)
    auth_repository = AuthRepository(db)
    service = DashboardService(repository, auth_repository)
    return DashboardController(service)


ControllerDep = Annotated[DashboardController, Depends(_build_controller)]


@router.get(
    "/admin/dashboard",
    response_model=AdminDashboardResponse,
    summary="Platform dashboard aggregates for admins.",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def admin_dashboard(
    controller: ControllerDep,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
) -> AdminDashboardResponse:
    return await controller.admin(days)


@router.get(
    "/dashboard",
    response_model=UserDashboardResponse,
    summary="Authenticated user dashboard aggregates.",
)
async def user_dashboard(
    current_user: CurrentUserDep,
    controller: ControllerDep,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
) -> UserDashboardResponse:
    return await controller.me(current_user, days)


__all__ = ["router"]
