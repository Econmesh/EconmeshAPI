"""DTOs for the conversations module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import Query
from pydantic import Field

from src.modules.conversations.model import (
    ConversationAuthorRole,
    ConversationMessageType,
    ConversationStatus,
    ConversationSystemEventKind,
)
from src.shared.schemas.base import APIModel


class ConversationCreate(APIModel):
    opportunity_id: UUID
    company_id: UUID
    message: str | None = Field(default=None, min_length=1, max_length=5000)


class ConversationMessageCreate(APIModel):
    body: str = Field(..., min_length=1, max_length=5000)


class ConversationInternalNoteCreate(APIModel):
    body: str = Field(..., min_length=1, max_length=5000)


class ConversationCloseRequest(APIModel):
    reason: str | None = Field(default=None, max_length=2000)


class ConversationRequestReopen(APIModel):
    message: str | None = Field(default=None, max_length=2000)


class ConversationRespondReopen(APIModel):
    accept: bool
    message: str | None = Field(default=None, max_length=2000)


class ConversationRequestNewContact(APIModel):
    message: str | None = Field(default=None, max_length=2000)


class ConversationRespondNewContact(APIModel):
    accept: bool
    message: str | None = Field(default=None, max_length=2000)


class ConversationMessageResponse(APIModel):
    id: UUID
    conversation_id: UUID
    author_id: UUID
    author_company_id: UUID | None = None
    author_role: ConversationAuthorRole
    author_name: str | None = None
    message_type: ConversationMessageType
    body: str
    read_at: datetime | None = None
    created_at: datetime
    event_kind: ConversationSystemEventKind | None = None
    event_actor_user_id: UUID | None = None
    event_actor_name: str | None = None
    event_reason: str | None = None


class ConversationMessageListResponse(APIModel):
    items: list[ConversationMessageResponse]
    total: int


class ConversationResponse(APIModel):
    id: UUID
    opportunity_id: UUID
    opportunity_title: str
    offerer_company_id: UUID
    offerer_company_name: str
    offerer_user_id: UUID
    interested_company_id: UUID
    interested_company_name: str
    interested_user_id: UUID
    created_by_user_id: UUID
    status: ConversationStatus
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    counterpart_company_name: str | None = None
    my_role: Literal["offerer", "interested"] | None = None
    closed_by_user_id: UUID | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None
    reopen_requested_by_user_id: UUID | None = None
    reopen_requested_at: datetime | None = None
    reopen_request_message: str | None = None
    new_contact_requested_by_user_id: UUID | None = None
    new_contact_requested_at: datetime | None = None
    new_contact_request_message: str | None = None
    is_active: bool = True
    replaced_by_conversation_id: UUID | None = None
    supersedes_conversation_id: UUID | None = None
    i_closed: bool = False
    can_reopen: bool = False
    can_request_reopen: bool = False
    can_respond_reopen: bool = False
    can_request_new_contact: bool = False
    can_respond_new_contact: bool = False


class ConversationDetailResponse(ConversationResponse):
    offerer_user_name: str | None = None
    interested_user_name: str | None = None
    offerer_online: bool = False
    interested_online: bool = False


class ConversationListResponse(APIModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class AdminConversationListParams(APIModel):
    page: int = 1
    page_size: int = 20
    status: ConversationStatus | None = None
    q: str | None = None

    @classmethod
    def as_query(
        cls,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        status: ConversationStatus | None = Query(default=None),
        q: str | None = Query(default=None, max_length=200),
    ) -> AdminConversationListParams:
        return cls(page=page, page_size=page_size, status=status, q=q)


class UserConversationListParams(APIModel):
    page: int = 1
    page_size: int = 20
    status: ConversationStatus | None = None

    @classmethod
    def as_query(
        cls,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        status: ConversationStatus | None = Query(default=None),
    ) -> UserConversationListParams:
        return cls(page=page, page_size=page_size, status=status)


class ConversationStreamEvent(APIModel):
    type: Literal[
        "conversation_created",
        "message_created",
        "messages_read",
        "presence_changed",
        "conversation_updated",
        "ping",
    ]
    data: dict[str, object] = Field(default_factory=dict)


__all__ = [
    "AdminConversationListParams",
    "ConversationCloseRequest",
    "ConversationCreate",
    "ConversationDetailResponse",
    "ConversationInternalNoteCreate",
    "ConversationListResponse",
    "ConversationMessageCreate",
    "ConversationMessageListResponse",
    "ConversationMessageResponse",
    "ConversationRequestNewContact",
    "ConversationRequestReopen",
    "ConversationRespondNewContact",
    "ConversationRespondReopen",
    "ConversationResponse",
    "ConversationStreamEvent",
    "UserConversationListParams",
]
