"""DTOs for the ``users`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.shared.schemas.base import APIModel


class UserProfileCreate(APIModel):
    company_id: UUID | None = None
    phone: str | None = None
    job_title: str | None = None
    locale: str = "en-US"


class UserProfileUpdate(APIModel):
    company_id: UUID | None = None
    phone: str | None = None
    job_title: str | None = None
    locale: str | None = None


class UserProfileResponse(APIModel):
    id: UUID
    user_id: UUID
    company_id: UUID | None = None
    phone: str | None = None
    job_title: str | None = None
    locale: str
    created_at: datetime
    updated_at: datetime


__all__ = ["UserProfileCreate", "UserProfileResponse", "UserProfileUpdate"]
