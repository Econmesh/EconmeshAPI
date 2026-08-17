"""DTOs for platform settings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.shared.schemas.base import APIModel


class PlatformSettingsUpdate(APIModel):
    require_signature_authorization: bool | None = None


class PlatformSettingsResponse(APIModel):
    id: UUID
    require_signature_authorization: bool
    updated_at: datetime


__all__ = ["PlatformSettingsResponse", "PlatformSettingsUpdate"]
