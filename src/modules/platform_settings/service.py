"""Business rules for platform settings."""

from __future__ import annotations

from src.modules.platform_settings.model import PlatformSettingsDocument
from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.modules.platform_settings.schema import (
    PlatformSettingsResponse,
    PlatformSettingsUpdate,
)


class PlatformSettingsService:
    def __init__(self, repository: PlatformSettingsRepository) -> None:
        self._repo = repository

    async def get(self) -> PlatformSettingsResponse:
        settings = await self._repo.get_or_create()
        return self._to_response(settings)

    async def update(self, payload: PlatformSettingsUpdate) -> PlatformSettingsResponse:
        patch = payload.model_dump(exclude_unset=True)
        settings = await self._repo.update(patch)
        return self._to_response(settings)

    @staticmethod
    def _to_response(settings: PlatformSettingsDocument) -> PlatformSettingsResponse:
        return PlatformSettingsResponse(
            id=settings.id,
            require_signature_authorization=settings.require_signature_authorization,
            updated_at=settings.updated_at,
        )


__all__ = ["PlatformSettingsService"]
