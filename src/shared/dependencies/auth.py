"""Authentication dependencies (Bearer token + Firebase verification)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from src.core.exceptions import AuthError
from src.core.firebase import firebase
from src.core.logging import user_id_ctx
from src.shared.constants.roles import DEFAULT_ROLE, Role

_bearer_scheme = HTTPBearer(auto_error=False, description="Firebase ID token")


class CurrentUser(BaseModel):
    """Lightweight identity object available to every authenticated route."""

    uid: str = Field(..., description="Firebase UID — stable, opaque.")
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    email_verified: bool = False
    role: Role = DEFAULT_ROLE
    claims: dict[str, object] = Field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN


def _role_from_claims(claims: dict[str, object]) -> Role:
    """Promote a Firebase custom claim to a typed ``Role``; fall back to default."""
    raw = claims.get("role")
    if isinstance(raw, str):
        try:
            return Role(raw)
        except ValueError:
            return DEFAULT_ROLE
    return DEFAULT_ROLE


async def get_current_user(
    request: Request,
    creds: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> CurrentUser:
    """Resolve the authenticated user from a ``Authorization: Bearer <token>`` header.

    Verification is delegated to the Firebase Admin SDK. The decoded claims
    are mapped to a typed ``CurrentUser`` and bound into the structlog
    request context.
    """
    if creds is None or not creds.credentials:
        raise AuthError("Missing bearer token.", code="missing_token")

    claims = await firebase.verify_id_token(creds.credentials)

    uid = str(claims["uid"])
    user = CurrentUser(
        uid=uid,
        email=claims.get("email"),
        name=claims.get("name"),
        picture=claims.get("picture"),
        email_verified=bool(claims.get("email_verified", False)),
        role=_role_from_claims(claims),
        claims=claims,
    )

    user_id_ctx.set(uid)
    request.state.user = user
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_optional_user(
    request: Request,
    creds: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> CurrentUser | None:
    """Like :func:`get_current_user` but returns ``None`` when no token is provided."""
    if creds is None or not creds.credentials:
        return None
    return await get_current_user(request, creds)


__all__ = [
    "CurrentUser",
    "CurrentUserDep",
    "get_current_user",
    "get_optional_user",
]
