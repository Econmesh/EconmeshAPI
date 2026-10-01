"""DTOs for platform settings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.platform_settings.model import DmcAssignmentMode, ForoFillMode
from src.shared.schemas.base import APIModel


class PlatformSettingsUpdate(APIModel):
    require_signature_authorization: bool | None = None
    foro_fill_mode: ForoFillMode | None = None
    foro_city: str | None = Field(default=None, max_length=120)
    foro_state: str | None = Field(default=None, max_length=2)
    dmc_assignment_mode: DmcAssignmentMode | None = None


class PlatformSettingsResponse(APIModel):
    id: UUID
    require_signature_authorization: bool
    foro_fill_mode: ForoFillMode = ForoFillMode.COMPANY
    foro_city: str | None = None
    foro_state: str | None = None
    dmc_assignment_mode: DmcAssignmentMode = DmcAssignmentMode.MANUAL
    updated_at: datetime


__all__ = ["PlatformSettingsResponse", "PlatformSettingsUpdate"]
