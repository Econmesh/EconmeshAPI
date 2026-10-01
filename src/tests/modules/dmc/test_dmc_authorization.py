"""Authorization, queue and scope tests for the DMC agent."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.core.exceptions import ForbiddenError, ValidationAppError
from src.modules.dmc.assignment import DmcAssignmentService
from src.modules.dmc.model import AuditAction, DmcAgentDocument
from src.modules.dmc.queue import QueueCandidate, next_in_queue
from src.modules.dmc.scope import PortfolioScope
from src.modules.platform_settings.model import DmcAssignmentMode, PlatformSettingsDocument
from src.modules.support.model import (
    SupportContactInterest,
    SupportTicketDocument,
    SupportTicketSource,
)
from src.shared.constants.permissions import Permission, role_has_permission
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUser, get_current_user

pytestmark = pytest.mark.unit


def _candidate(
    *,
    position: int,
    available: bool = True,
    is_active: bool = True,
    role: Role = Role.DMC_AGENT,
) -> QueueCandidate:
    return QueueCandidate(
        user_id=uuid4(),
        queue_position=position,
        available=available,
        is_active=is_active,
        role=role,
        created_at=datetime(2026, 1, position + 1, tzinfo=UTC),
    )


def test_round_robin_picks_lowest_position_and_skips_unavailable() -> None:
    unavailable = _candidate(position=0, available=False)
    inactive = _candidate(position=1, is_active=False)
    nxt = _candidate(position=2)
    later = _candidate(position=3)
    chosen = next_in_queue([unavailable, inactive, later, nxt])
    assert chosen is nxt
    assert next_in_queue([unavailable, inactive]) is None


def test_dmc_agent_permissions_exclude_admin_powers() -> None:
    assert role_has_permission(Role.DMC_AGENT, Permission.OPPORTUNITIES_READ)
    assert not role_has_permission(Role.DMC_AGENT, Permission.OPPORTUNITIES_WRITE)
    assert not role_has_permission(Role.DMC_AGENT, Permission.SUPPORT_ASSIGN)
    assert not role_has_permission(Role.DMC_AGENT, Permission.DMC_QUEUE_CONFIGURE)
    assert not role_has_permission(Role.DMC_AGENT, Permission.USERS_MANAGE)
    assert role_has_permission(Role.ADMIN, Permission.SUPPORT_ASSIGN)
    assert role_has_permission(Role.ADMIN, Permission.DASHBOARD_GLOBAL)


def test_portfolio_scope_rejects_foreign_company_and_user() -> None:
    scope = PortfolioScope(agent_user_id=uuid4())
    with pytest.raises(ForbiddenError) as company_error:
        scope.require_company(uuid4())
    assert company_error.value.code == "outside_scope"
    with pytest.raises(ForbiddenError) as user_error:
        scope.require_user(uuid4())
    assert user_error.value.code == "outside_scope"


async def test_dmc_agent_cannot_call_admin_routes(
    app: FastAPI, client: AsyncClient
) -> None:
    async def _override() -> CurrentUser:
        return CurrentUser(
            uid="firebase-dmc",
            email="agent@example.com",
            role=Role.DMC_AGENT,
            email_verified=True,
        )

    app.dependency_overrides[get_current_user] = _override
    try:
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "role_required"
    finally:
        app.dependency_overrides.clear()


async def test_viewer_cannot_call_dmc_routes(app: FastAPI, client: AsyncClient) -> None:
    async def _override() -> CurrentUser:
        return CurrentUser(
            uid="firebase-viewer",
            email="viewer@example.com",
            role=Role.VIEWER,
            email_verified=True,
        )

    app.dependency_overrides[get_current_user] = _override
    try:
        response = await client.get(
            "/api/v1/dmc/dashboard",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


async def test_admin_cannot_use_agent_router(app: FastAPI, client: AsyncClient) -> None:
    async def _override() -> CurrentUser:
        return CurrentUser(
            uid="firebase-admin",
            email="admin@example.com",
            role=Role.ADMIN,
            email_verified=True,
        )

    app.dependency_overrides[get_current_user] = _override
    try:
        response = await client.get(
            "/api/v1/dmc/companies",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


async def test_automatic_assignment_rotates_selected_agent() -> None:
    agent_user_id = uuid4()
    ticket = SupportTicketDocument(
        source=SupportTicketSource.CONTACT_REQUEST,
        interest=SupportContactInterest.DMC,
        ticket_number=1,
        subject="Contato DMC",
    )
    agent_doc = DmcAgentDocument(user_id=agent_user_id, available=True, queue_position=0)
    user = AsyncMock()
    user.id = agent_user_id
    user.role = Role.DMC_AGENT
    user.is_active = True
    user.email = "a@example.com"
    user.name = "Agente A"

    agents = AsyncMock()
    agents.get_by_user_id = AsyncMock(return_value=agent_doc)
    agents.next_queue_position = AsyncMock(return_value=4)
    agents.update = AsyncMock(return_value=agent_doc)
    tickets = AsyncMock()
    tickets.get_by_id = AsyncMock(return_value=ticket)

    async def _update(_ticket_id, fields):
        ticket.assigned_agent_id = fields["assigned_agent_id"]
        return ticket

    tickets.update = AsyncMock(side_effect=_update)
    notifications = AsyncMock()
    notifications.notify_dmc_agent_assigned = AsyncMock()
    audit = AsyncMock()
    audit.record = AsyncMock()
    service = DmcAssignmentService(
        agents=agents,
        auth=AsyncMock(),
        tickets=tickets,
        settings=AsyncMock(),
        notifications=notifications,
        audit=audit,
    )
    service._auth.get_by_id = AsyncMock(return_value=user)

    updated = await service.assign(
        ticket.id,
        agent_user_id=agent_user_id,
        mode="automatic",
        actor_user_id=None,
    )
    assert updated.assigned_agent_id == agent_user_id
    agents.update.assert_awaited()
    assert agents.update.await_args.args[1]["queue_position"] == 4
    audit.record.assert_awaited()
    assert audit.record.await_args.args[0] == AuditAction.TICKET_ASSIGNED


async def test_reassignment_records_previous_agent() -> None:
    previous = uuid4()
    nxt = uuid4()
    ticket = SupportTicketDocument(
        source=SupportTicketSource.CONTACT_REQUEST,
        interest=SupportContactInterest.DMC,
        ticket_number=8,
        subject="Contato",
        assigned_agent_id=previous,
    )
    user = AsyncMock()
    user.id = nxt
    user.role = Role.DMC_AGENT
    user.is_active = True
    user.name = "Agente B"
    user.email = "b@example.com"
    agents = AsyncMock()
    agents.get_by_user_id = AsyncMock(
        return_value=DmcAgentDocument(user_id=nxt, available=False, queue_position=1)
    )
    agents.update = AsyncMock()
    tickets = AsyncMock()
    tickets.get_by_id = AsyncMock(return_value=ticket)

    async def _update(_ticket_id, fields):
        ticket.assigned_agent_id = fields["assigned_agent_id"]
        return ticket

    tickets.update = AsyncMock(side_effect=_update)
    audit = AsyncMock()
    audit.record = AsyncMock()
    service = DmcAssignmentService(
        agents=agents,
        auth=AsyncMock(),
        tickets=tickets,
        settings=AsyncMock(),
        notifications=AsyncMock(),
        audit=audit,
    )
    service._auth.get_by_id = AsyncMock(return_value=user)
    await service.assign(ticket.id, agent_user_id=nxt, mode="manual", actor_user_id=uuid4())
    assert ticket.assigned_agent_id == nxt
    assert audit.record.await_args.args[0] == AuditAction.TICKET_REASSIGNED
    assert audit.record.await_args.kwargs["before"]["assigned_agent_id"] == previous


async def test_manual_mode_does_not_auto_assign() -> None:
    ticket = SupportTicketDocument(
        source=SupportTicketSource.CONTACT_REQUEST,
        interest=SupportContactInterest.DMC,
        ticket_number=2,
        subject="Contato",
    )
    settings = AsyncMock()
    settings.get_or_create = AsyncMock(
        return_value=PlatformSettingsDocument(dmc_assignment_mode=DmcAssignmentMode.MANUAL)
    )
    service = DmcAssignmentService(
        agents=AsyncMock(),
        auth=AsyncMock(),
        tickets=AsyncMock(),
        settings=settings,
        notifications=AsyncMock(),
        audit=AsyncMock(),
    )
    result = await service.handle_new_ticket(ticket)
    assert result is ticket
    assert ticket.assigned_agent_id is None


async def test_assign_rejects_non_dmc_ticket() -> None:
    ticket = SupportTicketDocument(
        source=SupportTicketSource.INTERNAL,
        interest=None,
        ticket_number=3,
        subject="Suporte",
    )
    tickets = AsyncMock()
    tickets.get_by_id = AsyncMock(return_value=ticket)
    service = DmcAssignmentService(
        agents=AsyncMock(),
        auth=AsyncMock(),
        tickets=tickets,
        settings=AsyncMock(),
        notifications=AsyncMock(),
        audit=AsyncMock(),
    )
    with pytest.raises(ValidationAppError):
        await service.assign(
            ticket.id, agent_user_id=uuid4(), mode="manual", actor_user_id=uuid4()
        )
