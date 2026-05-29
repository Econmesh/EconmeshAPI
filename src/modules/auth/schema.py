"""DTOs exchanged over HTTP for the ``auth`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from src.shared.constants.roles import Role
from src.shared.schemas.base import APIModel


class LoginRequest(APIModel):
    """Body for ``POST /auth/login`` — clients hand over the Firebase ID token."""

    id_token: str = Field(..., min_length=20, description="Firebase-issued ID token.")


class MeResponse(APIModel):
    """Identity envelope returned by ``GET /auth/me``."""

    id: UUID
    firebase_uid: str
    email: EmailStr | None = None
    name: str | None = None
    picture: str | None = None
    email_verified: bool = False
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class TokenIntrospectionResponse(APIModel):
    """Diagnostics returned by ``POST /auth/login`` so a client can debug tokens."""

    uid: str
    issuer: str | None = None
    audience: str | None = None
    expires_at: int | None = Field(default=None, description="Unix epoch seconds.")
    issued_at: int | None = None
    email_verified: bool = False


class LoginResponse(APIModel):
    """Full payload for ``POST /auth/login``: identity + token diagnostics."""

    user: MeResponse
    token: TokenIntrospectionResponse


__all__ = [
    "LoginRequest",
    "LoginResponse",
    "MeResponse",
    "TokenIntrospectionResponse",
]
