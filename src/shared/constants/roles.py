"""RBAC roles. Add new roles here and reference them via the enum."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Coarse-grained roles attached to a user.

    Fine-grained authorisation should be expressed via scopes/permissions
    when the role-based model proves insufficient.
    """

    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    VIEWER = "viewer"
    SERVICE = "service"
    DMC_AGENT = "dmc_agent"


DEFAULT_ROLE: Role = Role.VIEWER

# Roles allowed to sign in to the administrative panel.
PANEL_ROLES: frozenset[Role] = frozenset({Role.ADMIN, Role.DMC_AGENT})


__all__ = ["DEFAULT_ROLE", "PANEL_ROLES", "Role"]
