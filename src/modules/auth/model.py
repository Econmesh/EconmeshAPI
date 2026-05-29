"""Persistence model for the ``users`` collection."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import EmailStr, Field

from src.shared.constants.roles import DEFAULT_ROLE, Role
from src.shared.schemas.base import DomainDocument


class UserDocument(DomainDocument):
    """A user record synchronised from a Firebase identity."""

    collection_name: ClassVar[str] = "users"

    firebase_uid: str = Field(..., description="Stable Firebase UID.")
    email: EmailStr | None = None
    name: str | None = None
    picture: str | None = None
    email_verified: bool = False
    role: Role = DEFAULT_ROLE
    is_active: bool = True
    last_login_at: Any | None = None
    custom_claims: dict[str, Any] = Field(default_factory=dict)


__all__ = ["UserDocument"]
