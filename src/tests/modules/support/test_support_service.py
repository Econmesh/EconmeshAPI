"""Unit tests for support service business rules."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.core.exceptions import ForbiddenError, ValidationAppError
from src.modules.auth.model import UserDocument
from src.modules.support.model import (
    SupportMessageType,
    SupportTicketDocument,
    SupportTicketStatus,
)
from src.modules.support.schema import SupportMessageCreate
from src.modules.support.service import SupportService
from src.shared.constants.roles import Role
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit


def _build_service(
    *,
    ticket: SupportTicketDocument | None = None,
    user_id: UUID | None = None,
) -> tuple[SupportService, dict[str, AsyncMock]]:
    tickets_repo = AsyncMock()
    messages_repo = AsyncMock()
    auth_repo = AsyncMock()
    realtime = AsyncMock()
    notifications = AsyncMock()
    presence = AsyncMock()

    uid = user_id or new_uuid()
    user = UserDocument(
        id=uid,
        firebase_uid="fb-uid",
        email="user@example.com",
        name="User",
        role=Role.VIEWER,
    )
    auth_repo.get_by_firebase_uid.return_value = user
    auth_repo.get_by_id.return_value = user

    if ticket is None:
        ticket = SupportTicketDocument(
            user_id=uid,
            ticket_number=1,
            subject="Test",
            status=SupportTicketStatus.OPEN,
            last_message_at=utcnow(),
        )
    tickets_repo.get_by_id.return_value = ticket
    messages_repo.list_by_ticket.return_value = []

    service = SupportService(
        tickets_repo=tickets_repo,
        messages_repo=messages_repo,
        auth_repo=auth_repo,
        realtime=realtime,
        notifications=notifications,
        presence=presence,
    )
    mocks = {
        "tickets": tickets_repo,
        "messages": messages_repo,
        "auth": auth_repo,
        "realtime": realtime,
        "notifications": notifications,
        "presence": presence,
    }
    return service, mocks


async def test_user_cannot_access_other_users_ticket() -> None:
    other_user = new_uuid()
    ticket = SupportTicketDocument(
        user_id=other_user,
        ticket_number=1,
        subject="Private",
        status=SupportTicketStatus.OPEN,
    )
    service, _ = _build_service(ticket=ticket)

    with pytest.raises(ForbiddenError):
        await service.get_user_ticket(ticket.id, firebase_uid="fb-uid")


async def test_cannot_message_closed_ticket() -> None:
    ticket = SupportTicketDocument(
        user_id=new_uuid(),
        ticket_number=1,
        subject="Closed",
        status=SupportTicketStatus.CLOSED,
    )
    service, mocks = _build_service(ticket=ticket)
    mocks["auth"].get_by_firebase_uid.return_value = UserDocument(
        id=ticket.user_id,
        firebase_uid="fb-uid",
        email="u@example.com",
        role=Role.VIEWER,
    )

    with pytest.raises(ValidationAppError):
        await service.add_user_message(
            ticket.id,
            SupportMessageCreate(body="hello"),
            firebase_uid="fb-uid",
        )


async def test_list_user_messages_excludes_internal_notes() -> None:
    from src.modules.support.model import (
        SupportAuthorRole,
        SupportMessageDocument,
    )

    ticket_id = new_uuid()
    user_id = new_uuid()
    ticket = SupportTicketDocument(
        user_id=user_id,
        ticket_number=1,
        subject="T",
        status=SupportTicketStatus.OPEN,
    )
    service, mocks = _build_service(ticket=ticket, user_id=user_id)
    mocks["auth"].get_by_firebase_uid.return_value = UserDocument(
        id=user_id,
        firebase_uid="fb-uid",
        email="u@example.com",
        role=Role.VIEWER,
    )
    mocks["messages"].list_by_ticket.return_value = [
        SupportMessageDocument(
            ticket_id=ticket_id,
            author_id=user_id,
            author_role=SupportAuthorRole.USER,
            message_type=SupportMessageType.USER_MESSAGE,
            body="hi",
        ),
    ]

    result = await service.list_user_messages(ticket.id, firebase_uid="fb-uid")
    mocks["messages"].list_by_ticket.assert_awaited_once_with(
        ticket.id, user_visible_only=True
    )
    assert result.total == 1
    assert result.items[0].message_type == SupportMessageType.USER_MESSAGE
