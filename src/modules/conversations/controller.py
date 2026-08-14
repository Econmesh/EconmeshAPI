"""HTTP controllers for opportunity conversations."""

from __future__ import annotations

from uuid import UUID

from src.modules.conversations.schema import (
    AdminConversationListParams,
    ConversationCloseRequest,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationInternalNoteCreate,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationRequestNewContact,
    ConversationRequestReopen,
    ConversationRespondNewContact,
    ConversationRespondReopen,
    ConversationResponse,
    UserConversationListParams,
)
from src.modules.conversations.service import ConversationsService
from src.shared.dependencies.auth import CurrentUser


class UserConversationsController:
    def __init__(self, service: ConversationsService) -> None:
        self._service = service

    async def create_or_get(
        self, payload: ConversationCreate, current_user: CurrentUser
    ) -> ConversationResponse:
        return await self._service.create_or_get(
            payload, firebase_uid=current_user.uid
        )

    async def list_conversations(
        self, params: UserConversationListParams, current_user: CurrentUser
    ) -> ConversationListResponse:
        return await self._service.list_user_conversations(
            params, firebase_uid=current_user.uid
        )

    async def get_conversation(
        self, conversation_id: UUID, current_user: CurrentUser
    ) -> ConversationResponse:
        return await self._service.get_user_conversation(
            conversation_id, firebase_uid=current_user.uid
        )

    async def list_messages(
        self, conversation_id: UUID, current_user: CurrentUser
    ) -> ConversationMessageListResponse:
        return await self._service.list_user_messages(
            conversation_id, firebase_uid=current_user.uid
        )

    async def add_message(
        self,
        conversation_id: UUID,
        payload: ConversationMessageCreate,
        current_user: CurrentUser,
    ) -> ConversationMessageResponse:
        return await self._service.add_user_message(
            conversation_id, payload, firebase_uid=current_user.uid
        )

    async def mark_messages_read(
        self, conversation_id: UUID, current_user: CurrentUser
    ) -> ConversationMessageListResponse:
        return await self._service.mark_user_messages_read(
            conversation_id, firebase_uid=current_user.uid
        )

    async def close(
        self,
        conversation_id: UUID,
        payload: ConversationCloseRequest,
        current_user: CurrentUser,
    ) -> ConversationResponse:
        return await self._service.close_conversation(
            conversation_id, payload, firebase_uid=current_user.uid
        )

    async def reopen(
        self, conversation_id: UUID, current_user: CurrentUser
    ) -> ConversationResponse:
        return await self._service.reopen_conversation(
            conversation_id, firebase_uid=current_user.uid
        )

    async def request_reopen(
        self,
        conversation_id: UUID,
        payload: ConversationRequestReopen,
        current_user: CurrentUser,
    ) -> ConversationResponse:
        return await self._service.request_reopen(
            conversation_id, payload, firebase_uid=current_user.uid
        )

    async def respond_reopen(
        self,
        conversation_id: UUID,
        payload: ConversationRespondReopen,
        current_user: CurrentUser,
    ) -> ConversationResponse:
        return await self._service.respond_reopen(
            conversation_id, payload, firebase_uid=current_user.uid
        )

    async def request_new_contact(
        self,
        conversation_id: UUID,
        payload: ConversationRequestNewContact,
        current_user: CurrentUser,
    ) -> ConversationResponse:
        return await self._service.request_new_contact(
            conversation_id, payload, firebase_uid=current_user.uid
        )

    async def respond_new_contact(
        self,
        conversation_id: UUID,
        payload: ConversationRespondNewContact,
        current_user: CurrentUser,
    ) -> ConversationResponse:
        return await self._service.respond_new_contact(
            conversation_id, payload, firebase_uid=current_user.uid
        )


class AdminConversationsController:
    def __init__(self, service: ConversationsService) -> None:
        self._service = service

    async def list_conversations(
        self, params: AdminConversationListParams
    ) -> ConversationListResponse:
        return await self._service.list_admin_conversations(params)

    async def get_conversation(
        self, conversation_id: UUID
    ) -> ConversationDetailResponse:
        return await self._service.get_admin_conversation(conversation_id)

    async def list_messages(
        self, conversation_id: UUID
    ) -> ConversationMessageListResponse:
        return await self._service.list_admin_messages(conversation_id)

    async def add_note(
        self,
        conversation_id: UUID,
        payload: ConversationInternalNoteCreate,
        current_user: CurrentUser,
    ) -> ConversationMessageResponse:
        return await self._service.add_internal_note(
            conversation_id, payload, firebase_uid=current_user.uid
        )


__all__ = ["AdminConversationsController", "UserConversationsController"]
