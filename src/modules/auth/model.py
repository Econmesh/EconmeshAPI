"""Persistence models for the ``users`` and ``email_verifications`` collections."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import EmailStr, Field

from src.shared.constants.roles import DEFAULT_ROLE, Role
from src.shared.schemas.base import DomainDocument


class UserDocument(DomainDocument):
    """A user record. Credentials live in Firebase; this is the domain mirror."""

    collection_name: ClassVar[str] = "users"

    firebase_uid: str = Field(..., description="Stable Firebase UID.")
    email: EmailStr | None = None
    name: str | None = None
    phone: str | None = None
    picture: str | None = None
    email_verified: bool = False
    is_verified: bool = Field(
        default=False,
        description="Whether the user confirmed their account (gate for login).",
    )
    role: Role = DEFAULT_ROLE
    is_active: bool = True
    last_login_at: Any | None = None
    custom_claims: dict[str, Any] = Field(default_factory=dict)


class EmailVerificationDocument(DomainDocument):
    """A single-use, time-boxed account-confirmation token (hash stored only)."""

    collection_name: ClassVar[str] = "email_verifications"

    user_id: UUID = Field(..., description="FK to users._id")
    firebase_uid: str
    email: EmailStr
    token_hash: str = Field(..., description="SHA-256 of the raw token; raw never stored.")
    expires_at: datetime
    consumed_at: datetime | None = None


__all__ = ["EmailVerificationDocument", "UserDocument"]
