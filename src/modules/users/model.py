"""Persistence model for ``user_profiles``."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument


class UserProfileDocument(DomainDocument):
    """Extended profile attached to a user (1:1 with ``users``)."""

    collection_name: ClassVar[str] = "user_profiles"

    user_id: UUID = Field(..., description="FK to users._id")
    company_id: UUID | None = None
    phone: str | None = None
    job_title: str | None = None
    locale: str = "en-US"
    preferences: dict[str, object] = Field(default_factory=dict)


__all__ = ["UserProfileDocument"]
