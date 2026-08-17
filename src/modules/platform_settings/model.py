"""Persistence model for global platform settings."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument

PLATFORM_SETTINGS_ID = UUID("00000000-0000-4000-8000-000000000002")


class ForoFillMode(StrEnum):
    ADMIN = "admin"
    COMPANY = "company"


class PlatformSettingsDocument(DomainDocument):
    collection_name: ClassVar[str] = "platform_settings"

    id: UUID = Field(default=PLATFORM_SETTINGS_ID, alias="_id")
    require_signature_authorization: bool = False
    foro_fill_mode: ForoFillMode = ForoFillMode.COMPANY
    foro_city: str | None = None
    foro_state: str | None = None


__all__ = ["ForoFillMode", "PLATFORM_SETTINGS_ID", "PlatformSettingsDocument"]
