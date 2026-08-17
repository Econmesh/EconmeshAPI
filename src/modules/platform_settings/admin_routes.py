"""Admin routes for platform settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.modules.platform_settings.schema import (
    PlatformSettingsResponse,
    PlatformSettingsUpdate,
)
from src.modules.platform_settings.service import PlatformSettingsService
from src.shared.constants.roles import Role
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_role

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(
    prefix="/admin/platform",
    tags=["admin-platform-settings"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


def _build_service(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> PlatformSettingsService:
    return PlatformSettingsService(PlatformSettingsRepository(db))


ServiceDep = Annotated[PlatformSettingsService, Depends(_build_service)]


@router.get(
    "/settings",
    response_model=PlatformSettingsResponse,
    summary="Read global platform settings.",
    status_code=status.HTTP_200_OK,
)
async def get_platform_settings(service: ServiceDep) -> PlatformSettingsResponse:
    return await service.get()


@router.patch(
    "/settings",
    response_model=PlatformSettingsResponse,
    summary="Update global platform settings.",
    status_code=status.HTTP_200_OK,
)
async def update_platform_settings(
    payload: PlatformSettingsUpdate, service: ServiceDep
) -> PlatformSettingsResponse:
    return await service.update(payload)


__all__ = ["router"]
