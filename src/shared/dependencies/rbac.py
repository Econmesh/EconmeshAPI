"""Role-based access control dependencies.

Usage::

    @router.get("/admin", dependencies=[Depends(require_role(Role.ADMIN))])
    async def admin_only(): ...
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends

from src.core.exceptions import ForbiddenError
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUser, get_current_user


def require_role(
    *allowed: Role,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    """Build a dependency that enforces the caller has one of ``allowed`` roles."""
    allowed_set: frozenset[Role] = frozenset(allowed)

    async def _dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if user.role not in allowed_set:
            raise ForbiddenError(
                f"Role '{user.role}' is not allowed for this resource.",
                code="role_required",
                details={"required_roles": sorted(r.value for r in allowed_set)},
            )
        return user

    return _dependency


def require_scopes(
    *scopes: str,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    """Build a dependency that enforces the caller has all ``scopes`` (custom claims)."""
    needed: frozenset[str] = frozenset(scopes)

    async def _dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        claim_scopes = user.claims.get("scopes")
        owned: set[str]
        if isinstance(claim_scopes, list):
            owned = {str(s) for s in claim_scopes}
        elif isinstance(claim_scopes, str):
            owned = set(claim_scopes.split())
        else:
            owned = set()

        missing = needed - owned
        if missing:
            raise ForbiddenError(
                "Missing required scopes.",
                code="scope_required",
                details={"missing": sorted(missing)},
            )
        return user

    return _dependency


__all__ = ["require_role", "require_scopes"]
