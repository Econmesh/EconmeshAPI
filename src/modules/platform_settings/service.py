"""Business rules for platform settings."""

from __future__ import annotations

from src.core.exceptions import ValidationAppError
from src.modules.platform_settings.model import ForoFillMode, PlatformSettingsDocument
from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.modules.platform_settings.schema import (
    PlatformSettingsResponse,
    PlatformSettingsUpdate,
)
from src.shared.constants.brazil_states import STATE_NEIGHBORS


class PlatformSettingsService:
    def __init__(self, repository: PlatformSettingsRepository) -> None:
        self._repo = repository

    async def get(self) -> PlatformSettingsResponse:
        settings = await self._repo.get_or_create()
        return self._to_response(settings)

    async def update(self, payload: PlatformSettingsUpdate) -> PlatformSettingsResponse:
        patch = payload.model_dump(exclude_unset=True)
        current = await self._repo.get_or_create()
        mode = patch.get("foro_fill_mode", current.foro_fill_mode)
        if mode == ForoFillMode.ADMIN or mode == ForoFillMode.ADMIN.value:
            city = patch.get("foro_city", current.foro_city)
            state = patch.get("foro_state", current.foro_state)
            city = (city or "").strip()
            state = (state or "").strip().upper()
            if not city:
                raise ValidationAppError(
                    "Informe a cidade do foro quando o administrador preenche a comarca."
                )
            if state not in STATE_NEIGHBORS:
                raise ValidationAppError(
                    "Informe um estado (UF) válido para o foro."
                )
            patch["foro_city"] = city
            patch["foro_state"] = state
        elif "foro_state" in patch and patch["foro_state"]:
            state = str(patch["foro_state"]).strip().upper()
            if state not in STATE_NEIGHBORS:
                raise ValidationAppError("Informe um estado (UF) válido para o foro.")
            patch["foro_state"] = state
        settings = await self._repo.update(patch)
        return self._to_response(settings)

    @staticmethod
    def _to_response(settings: PlatformSettingsDocument) -> PlatformSettingsResponse:
        return PlatformSettingsResponse(
            id=settings.id,
            require_signature_authorization=settings.require_signature_authorization,
            foro_fill_mode=settings.foro_fill_mode,
            foro_city=settings.foro_city,
            foro_state=settings.foro_state,
            updated_at=settings.updated_at,
        )


__all__ = ["PlatformSettingsService"]
