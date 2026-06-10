"""Persistence model for ``user_profiles``."""

from __future__ import annotations

from datetime import date
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.schemas.base import DomainDocument


class UserProfileAddress(BaseModel):
    """Structured postal address for a user profile."""

    postal_code: str | None = Field(default=None, description="CEP / postal code.")
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class UserProfileDocument(DomainDocument):
    """Extended profile attached to a user (1:1 with ``users``)."""

    collection_name: ClassVar[str] = "user_profiles"

    user_id: UUID = Field(..., description="FK to users._id")
    company_id: UUID | None = None
    cpf: str | None = None
    birth_date: date | None = None
    job_title: str | None = None
    address: UserProfileAddress | None = None
    country: str = Field(default="BR", min_length=2, max_length=2)
    picture_storage_key: str | None = None
    picture_url: str | None = None
    locale: str = "pt-BR"
    preferences: dict[str, object] = Field(default_factory=dict)


__all__ = ["UserProfileAddress", "UserProfileDocument"]
