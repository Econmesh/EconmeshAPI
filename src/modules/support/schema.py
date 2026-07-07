"""DTOs for the support module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import Query
from pydantic import Field

from src.modules.support.model import (
    SupportAuthorRole,
    SupportMessageType,
    SupportTicketStatus,
)
from src.shared.schemas.base import APIModel


class SupportTicketCreate(APIModel):
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=1, max_length=5000)


class SupportMessageCreate(APIModel):
    body: str = Field(..., min_length=1, max_length=5000)


class SupportInternalNoteCreate(APIModel):
    body: str = Field(..., min_length=1, max_length=5000)


class SupportTicketAssign(APIModel):
    admin_id: UUID | None = None


class SupportMessageResponse(APIModel):
    id: UUID
    ticket_id: UUID
    author_id: UUID
    author_role: SupportAuthorRole
    author_name: str | None = None
    message_type: SupportMessageType
    body: str
    read_at: datetime | None = None
    created_at: datetime


class SupportMessageListResponse(APIModel):
    items: list[SupportMessageResponse]
    total: int


class SupportTicketResponse(APIModel):
    id: UUID
    user_id: UUID
    ticket_number: int
    subject: str
    status: SupportTicketStatus
    assigned_admin_id: UUID | None = None
    assigned_admin_name: str | None = None
    closed_by: UUID | None = None
    closed_at: datetime | None = None
    last_message_at: datetime | None = None
    last_responder_admin_id: UUID | None = None
    last_responder_admin_name: str | None = None
    created_at: datetime
    updated_at: datetime


class SupportTicketDetailResponse(SupportTicketResponse):
    user_name: str | None = None
    user_email: str | None = None
    user_online: bool = False


class SupportTicketListResponse(APIModel):
    items: list[SupportTicketResponse]
    total: int
    page: int
    page_size: int


class AdminSupportTicketListParams(APIModel):
    page: int = 1
    page_size: int = 20
    status: SupportTicketStatus | None = None
    q: str | None = None

    @classmethod
    def as_query(
        cls,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        status: SupportTicketStatus | None = Query(default=None),
        q: str | None = Query(default=None, max_length=200),
    ) -> AdminSupportTicketListParams:
        params = cls(page=page, page_size=page_size, status=status, q=q)
        # #region agent log
        import json, time
        from pathlib import Path
        _log_path = Path(__file__).resolve().parents[3] / "debug-499439.log"
        with _log_path.open("a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId": "499439", "runId": "post-fix", "hypothesisId": "B", "location": "schema.py:AdminSupportTicketListParams.as_query", "message": "status after APIModel construction", "data": {"query_status": status, "query_status_type": type(status).__name__ if status is not None else None, "params_status": params.status, "params_status_type": type(params.status).__name__ if params.status is not None else None}, "timestamp": int(time.time() * 1000)}) + "\n")
        # #endregion
        return params


class UserSupportTicketListParams(APIModel):
    page: int = 1
    page_size: int = 20
    status: SupportTicketStatus | None = None

    @classmethod
    def as_query(
        cls,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        status: SupportTicketStatus | None = Query(default=None),
    ) -> UserSupportTicketListParams:
        return cls(page=page, page_size=page_size, status=status)


class SupportStreamEvent(APIModel):
    type: Literal[
        "ticket_created",
        "message_created",
        "ticket_closed",
        "ticket_assigned",
        "ticket_reopened",
        "messages_read",
        "presence_changed",
        "ping",
    ]
    data: dict[str, object] = Field(default_factory=dict)


__all__ = [
    "AdminSupportTicketListParams",
    "SupportInternalNoteCreate",
    "SupportMessageCreate",
    "SupportMessageListResponse",
    "SupportMessageResponse",
    "SupportStreamEvent",
    "SupportTicketAssign",
    "SupportTicketCreate",
    "SupportTicketDetailResponse",
    "SupportTicketListResponse",
    "SupportTicketResponse",
    "UserSupportTicketListParams",
]
