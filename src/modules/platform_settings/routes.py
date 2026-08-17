"""Authenticated routes for reading platform settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.modules.platform_settings.schema import PlatformSettingsResponse
from src.modules.platform_settings.service import PlatformSettingsService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/platform", tags=["platform-settings"])


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
async def get_platform_settings(
    service: ServiceDep,
    _current_user: CurrentUserDep,
) -> PlatformSettingsResponse:
    return await service.get()


__all__ = ["router"]
