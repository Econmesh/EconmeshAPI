"""Static RBAC permission matrix.

Permissions are attached to roles in code. Data scope (which companies, users
and tickets a DMC agent may touch) is enforced separately in the DMC services
and is never taken from the client.
"""

from __future__ import annotations

from enum import StrEnum

from src.shared.constants.roles import Role


class Permission(StrEnum):
    DASHBOARD_GLOBAL = "dashboard.global"
    DASHBOARD_DMC = "dashboard.dmc"
    USERS_MANAGE = "users.manage"
    DMC_AGENTS_MANAGE = "dmc_agents.manage"
    COMPANIES_READ = "companies.read"
    COMPANIES_SEARCH = "companies.search"
    COMPANIES_PRE_REGISTER = "companies.pre_register"
    DIAGNOSTICS_MANAGE = "diagnostics.manage"
    OPPORTUNITIES_READ = "opportunities.read"
    OPPORTUNITIES_WRITE = "opportunities.write"
    DMC_CONVERSATIONS_READ = "dmc_conversations.read"
    DMC_CONVERSATIONS_SEND = "dmc_conversations.send"
    NOTIFICATIONS_READ = "notifications.read"
    NOTIFICATIONS_SEND = "notifications.send"
    NOTIFICATIONS_BROADCAST = "notifications.broadcast"
    SUPPORT_DMC_READ = "support.dmc.read"
    SUPPORT_DMC_RESPOND = "support.dmc.respond"
    SUPPORT_ASSIGN = "support.assign"
    DMC_QUEUE_CONFIGURE = "dmc.queue.configure"
    SETTINGS_GLOBAL = "settings.global"
    AUDIT_READ = "audit.read"


_DMC_AGENT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.DASHBOARD_DMC,
        Permission.COMPANIES_READ,
        Permission.COMPANIES_SEARCH,
        Permission.COMPANIES_PRE_REGISTER,
        Permission.DIAGNOSTICS_MANAGE,
        Permission.OPPORTUNITIES_READ,
        Permission.DMC_CONVERSATIONS_READ,
        Permission.DMC_CONVERSATIONS_SEND,
        Permission.NOTIFICATIONS_READ,
        Permission.NOTIFICATIONS_SEND,
        Permission.SUPPORT_DMC_READ,
        Permission.SUPPORT_DMC_RESPOND,
    }
)

_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(Permission)


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: _ADMIN_PERMISSIONS,
    Role.DMC_AGENT: _DMC_AGENT_PERMISSIONS,
}


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: Role, permission: Permission) -> bool:
    return permission in permissions_for(role)


__all__ = ["Permission", "ROLE_PERMISSIONS", "permissions_for", "role_has_permission"]
