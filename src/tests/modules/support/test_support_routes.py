"""Tests for the support module routes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.modules.support.controller import AdminSupportController, UserSupportController
from src.modules.support.model import (
    SupportAuthorRole,
    SupportMessageType,
    SupportTicketStatus,
)
from src.modules.support.routes import _build_controller
from src.modules.support.schema import (
    SupportMessageListResponse,
    SupportMessageResponse,
    SupportTicketDetailResponse,
    SupportTicketResponse,
)
from src.modules.admin.routes import _build_support_controller
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUser, get_current_user
from src.shared.utils.ids import new_uuid

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_TICKET_ID = new_uuid()
_USER_ID = new_uuid()
_ADMIN_ID = new_uuid()


def _sample_ticket() -> SupportTicketResponse:
    return SupportTicketResponse(
        id=_TICKET_ID,
        user_id=_USER_ID,
        ticket_number=1,
        subject="Problema no login",
        status=SupportTicketStatus.OPEN,
        assigned_admin_id=None,
        assigned_admin_name=None,
        closed_by=None,
        closed_at=None,
        last_message_at=_NOW,
        last_responder_admin_id=None,
        last_responder_admin_name=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _sample_message(
    *,
    message_type: SupportMessageType = SupportMessageType.USER_MESSAGE,
) -> SupportMessageResponse:
    return SupportMessageResponse(
        id=new_uuid(),
        ticket_id=_TICKET_ID,
        author_id=_USER_ID,
        author_role=SupportAuthorRole.USER,
        author_name="Alice",
        message_type=message_type,
        body="Preciso de ajuda",
        created_at=_NOW,
    )


async def test_create_ticket_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/support/tickets",
        json={"subject": "Test", "message": "Hello"},
    )
    assert response.status_code == 401


async def test_create_ticket_returns_201(app: FastAPI, client: AsyncClient) -> None:
    ticket = _sample_ticket()

    class _Stub(UserSupportController):
        def __init__(self) -> None:
            pass

        async def create_ticket(
            self, payload, current_user: CurrentUser
        ) -> SupportTicketResponse:
            assert payload.subject == "Problema no login"
            assert current_user.uid == "firebase-user"
            return ticket

    async def _user() -> CurrentUser:
        return CurrentUser(uid="firebase-user", email="alice@example.com")

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[_build_controller] = lambda: _Stub()
    try:
        response = await client.post(
            "/api/v1/support/tickets",
            json={"subject": "Problema no login", "message": "Não consigo entrar"},
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["ticket_number"] == 1
        assert body["subject"] == "Problema no login"
    finally:
        app.dependency_overrides.clear()


async def test_list_user_messages_stub(app: FastAPI, client: AsyncClient) -> None:
    user_msg = _sample_message(message_type=SupportMessageType.USER_MESSAGE)
    admin_msg = _sample_message(message_type=SupportMessageType.ADMIN_REPLY)

    class _Stub(UserSupportController):
        def __init__(self) -> None:
            pass

        async def list_messages(
            self, ticket_id: UUID, current_user: CurrentUser
        ) -> SupportMessageListResponse:
            assert ticket_id == _TICKET_ID
            return SupportMessageListResponse(items=[user_msg, admin_msg], total=2)

    async def _user() -> CurrentUser:
        return CurrentUser(uid="firebase-user", email="alice@example.com")

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[_build_controller] = lambda: _Stub()
    try:
        response = await client.get(
            f"/api/v1/support/tickets/{_TICKET_ID}/messages",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        types = {item["message_type"] for item in items}
        assert types == {"user_message", "admin_reply"}
        assert "internal_note" not in types
    finally:
        app.dependency_overrides.clear()


async def test_admin_list_tickets_requires_admin(app: FastAPI, client: AsyncClient) -> None:
    async def _viewer() -> CurrentUser:
        return CurrentUser(
            uid="firebase-viewer",
            email="v@example.com",
            role=Role.VIEWER,
        )

    app.dependency_overrides[get_current_user] = _viewer
    try:
        response = await client.get(
            "/api/v1/admin/support/tickets",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


async def test_admin_add_internal_note(app: FastAPI, client: AsyncClient) -> None:
    note = _sample_message(message_type=SupportMessageType.INTERNAL_NOTE)
    note = note.model_copy(update={"author_role": SupportAuthorRole.ADMIN})

    class _Stub(AdminSupportController):
        def __init__(self) -> None:
            pass

        async def add_note(self, ticket_id, payload, current_user: CurrentUser):
            assert ticket_id == _TICKET_ID
            assert payload.body == "Cliente VIP"
            return note

    async def _admin() -> CurrentUser:
        return CurrentUser(
            uid="firebase-admin",
            email="admin@example.com",
            role=Role.ADMIN,
        )

    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[_build_support_controller] = lambda: _Stub()
    try:
        response = await client.post(
            f"/api/v1/admin/support/tickets/{_TICKET_ID}/notes",
            json={"body": "Cliente VIP"},
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 201
        assert response.json()["message_type"] == "internal_note"
    finally:
        app.dependency_overrides.clear()


async def test_admin_close_ticket(app: FastAPI, client: AsyncClient) -> None:
    closed = _sample_ticket().model_copy(
        update={"status": SupportTicketStatus.CLOSED, "closed_by": _ADMIN_ID}
    )

    class _Stub(AdminSupportController):
        def __init__(self) -> None:
            pass

        async def close(self, ticket_id: UUID, current_user: CurrentUser):
            assert ticket_id == _TICKET_ID
            return closed

    async def _admin() -> CurrentUser:
        return CurrentUser(
            uid="firebase-admin",
            email="admin@example.com",
            role=Role.ADMIN,
        )

    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[_build_support_controller] = lambda: _Stub()
    try:
        response = await client.patch(
            f"/api/v1/admin/support/tickets/{_TICKET_ID}/close",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "closed"
    finally:
        app.dependency_overrides.clear()


async def test_admin_ticket_detail_includes_online(app: FastAPI, client: AsyncClient) -> None:
    detail = SupportTicketDetailResponse(
        **_sample_ticket().model_dump(),
        user_name="Alice",
        user_email="alice@example.com",
        user_online=True,
    )

    class _Stub(AdminSupportController):
        def __init__(self) -> None:
            pass

        async def get_ticket(self, ticket_id: UUID):
            return detail

    async def _admin() -> CurrentUser:
        return CurrentUser(uid="firebase-admin", email="admin@example.com", role=Role.ADMIN)

    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[_build_support_controller] = lambda: _Stub()
    try:
        response = await client.get(
            f"/api/v1/admin/support/tickets/{_TICKET_ID}",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user_online"] is True
        assert body["user_email"] == "alice@example.com"
    finally:
        app.dependency_overrides.clear()
