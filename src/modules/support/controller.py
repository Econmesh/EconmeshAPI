"""HTTP controllers for support."""

from __future__ import annotations

from uuid import UUID

from src.modules.support.schema import (
    AdminSupportTicketListParams,
    ExternalSupportContactCreate,
    PublicContactRequestCreate,
    SupportInternalNoteCreate,
    SupportMessageCreate,
    SupportMessageListResponse,
    SupportMessageResponse,
    SupportTicketAssign,
    SupportTicketCreate,
    SupportTicketDetailResponse,
    SupportTicketListResponse,
    SupportTicketResponse,
    UserSupportTicketListParams,
)
from src.modules.support.service import SupportService
from src.shared.dependencies.auth import CurrentUser
from src.shared.schemas.responses import MessageResponse


class UserSupportController:
    def __init__(self, service: SupportService) -> None:
        self._service = service

    async def create_ticket(
        self, payload: SupportTicketCreate, current_user: CurrentUser
    ) -> SupportTicketResponse:
        return await self._service.create_ticket(payload, firebase_uid=current_user.uid)

    async def list_tickets(
        self, params: UserSupportTicketListParams, current_user: CurrentUser
    ) -> SupportTicketListResponse:
        return await self._service.list_user_tickets(
            params, firebase_uid=current_user.uid
        )

    async def get_ticket(
        self, ticket_id: UUID, current_user: CurrentUser
    ) -> SupportTicketResponse:
        return await self._service.get_user_ticket(
            ticket_id, firebase_uid=current_user.uid
        )

    async def list_messages(
        self, ticket_id: UUID, current_user: CurrentUser
    ) -> SupportMessageListResponse:
        return await self._service.list_user_messages(
            ticket_id, firebase_uid=current_user.uid
        )

    async def add_message(
        self, ticket_id: UUID, payload: SupportMessageCreate, current_user: CurrentUser
    ) -> SupportMessageResponse:
        return await self._service.add_user_message(
            ticket_id, payload, firebase_uid=current_user.uid
        )

    async def heartbeat(self, current_user: CurrentUser) -> MessageResponse:
        await self._service.touch_presence(firebase_uid=current_user.uid)
        return MessageResponse(message="ok")

    async def go_offline(self, current_user: CurrentUser) -> MessageResponse:
        await self._service.clear_presence(firebase_uid=current_user.uid)
        return MessageResponse(message="ok")

    async def mark_messages_read(
        self, ticket_id: UUID, current_user: CurrentUser
    ) -> SupportMessageListResponse:
        return await self._service.mark_user_messages_read(
            ticket_id, firebase_uid=current_user.uid
        )


class PublicSupportController:
    def __init__(self, service: SupportService) -> None:
        self._service = service

    async def submit_contact(
        self, payload: ExternalSupportContactCreate
    ) -> MessageResponse:
        await self._service.create_external_contact(payload)
        return MessageResponse(message="Solicitação recebida com sucesso.")

    async def submit_contact_request(
        self, payload: PublicContactRequestCreate
    ) -> MessageResponse:
        await self._service.create_contact_request(payload)
        return MessageResponse(message="Solicitação recebida com sucesso.")


class AdminSupportController:
    def __init__(self, service: SupportService) -> None:
        self._service = service

    async def list_tickets(
        self, params: AdminSupportTicketListParams
    ) -> SupportTicketListResponse:
        return await self._service.list_admin_tickets(params)

    async def get_ticket(self, ticket_id: UUID) -> SupportTicketDetailResponse:
        return await self._service.get_admin_ticket(ticket_id)

    async def list_messages(self, ticket_id: UUID) -> SupportMessageListResponse:
        return await self._service.list_admin_messages(ticket_id)

    async def add_reply(
        self, ticket_id: UUID, payload: SupportMessageCreate, current_user: CurrentUser
    ) -> SupportMessageResponse:
        return await self._service.add_admin_reply(
            ticket_id, payload, firebase_uid=current_user.uid
        )

    async def add_note(
        self, ticket_id: UUID, payload: SupportInternalNoteCreate, current_user: CurrentUser
    ) -> SupportMessageResponse:
        return await self._service.add_internal_note(
            ticket_id, payload, firebase_uid=current_user.uid
        )

    async def assign(
        self, ticket_id: UUID, payload: SupportTicketAssign, current_user: CurrentUser
    ) -> SupportTicketResponse:
        return await self._service.assign_ticket(
            ticket_id, payload, firebase_uid=current_user.uid
        )

    async def close(
        self, ticket_id: UUID, current_user: CurrentUser
    ) -> SupportTicketResponse:
        return await self._service.close_ticket(ticket_id, firebase_uid=current_user.uid)

    async def reopen(
        self, ticket_id: UUID, current_user: CurrentUser
    ) -> SupportTicketResponse:
        return await self._service.reopen_ticket(ticket_id, firebase_uid=current_user.uid)

    async def mark_messages_read(
        self, ticket_id: UUID
    ) -> SupportMessageListResponse:
        return await self._service.mark_admin_messages_read(ticket_id)

    async def heartbeat(self, current_user: CurrentUser) -> MessageResponse:
        await self._service.touch_presence(firebase_uid=current_user.uid)
        return MessageResponse(message="ok")


__all__ = ["AdminSupportController", "PublicSupportController", "UserSupportController"]
