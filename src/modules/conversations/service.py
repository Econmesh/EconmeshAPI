"""Business logic for opportunity conversations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from src.infrastructure.realtime.conversation_pubsub import ConversationRealtimePublisher
from src.modules.auth.model import UserDocument
from src.modules.companies.repository import CompaniesRepository
from src.modules.conversations.model import (
    ConversationAuthorRole,
    ConversationMessageType,
    ConversationStatus,
    OpportunityConversationDocument,
    OpportunityConversationMessageDocument,
)
from src.modules.conversations.notification_service import ConversationNotificationService
from src.modules.conversations.repository import (
    ConversationMessagesRepository,
    ConversationsRepository,
)
from src.modules.conversations.schema import (
    AdminConversationListParams,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationInternalNoteCreate,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationResponse,
    UserConversationListParams,
)
from src.modules.opportunities.repository import OpportunitiesRepository
from src.shared.constants.roles import Role
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from src.infrastructure.realtime.presence import PresenceService
    from src.modules.auth.repository import AuthRepository


def _company_display_name(legal_name: str, trade_name: str | None) -> str:
    return trade_name.strip() if trade_name and trade_name.strip() else legal_name


def _message_to_response(
    doc: OpportunityConversationMessageDocument, *, author_name: str | None = None
) -> ConversationMessageResponse:
    return ConversationMessageResponse(
        id=doc.id,
        conversation_id=doc.conversation_id,
        author_id=doc.author_id,
        author_company_id=doc.author_company_id,
        author_role=doc.author_role,
        author_name=author_name,
        message_type=doc.message_type,
        body=doc.body,
        read_at=doc.read_at,
        created_at=doc.created_at,
    )


def _message_event_payload(response: ConversationMessageResponse) -> dict[str, object]:
    return {
        "id": str(response.id),
        "conversation_id": str(response.conversation_id),
        "author_id": str(response.author_id),
        "author_company_id": (
            str(response.author_company_id) if response.author_company_id else None
        ),
        "author_role": str(response.author_role),
        "author_name": response.author_name,
        "message_type": str(response.message_type),
        "body": response.body,
        "read_at": response.read_at.isoformat() if response.read_at else None,
        "created_at": response.created_at.isoformat(),
    }


class ConversationsService:
    def __init__(
        self,
        *,
        conversations_repo: ConversationsRepository,
        messages_repo: ConversationMessagesRepository,
        opportunities_repo: OpportunitiesRepository,
        companies_repo: CompaniesRepository,
        auth_repo: AuthRepository,
        realtime: ConversationRealtimePublisher | None,
        notifications: ConversationNotificationService,
        presence: PresenceService,
    ) -> None:
        self._conversations = conversations_repo
        self._messages = messages_repo
        self._opportunities = opportunities_repo
        self._companies = companies_repo
        self._auth = auth_repo
        self._realtime = realtime
        self._notifications = notifications
        self._presence = presence

    async def _resolve_user(self, firebase_uid: str) -> UserDocument:
        user = await self._auth.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def _resolve_admin(self, firebase_uid: str) -> UserDocument:
        user = await self._resolve_user(firebase_uid)
        if user.role != Role.ADMIN:
            raise ForbiddenError("Admin access required.")
        return user

    async def _user_name(self, user_id: UUID) -> str | None:
        user = await self._auth.get_by_id(user_id)
        if user is None:
            return None
        return user.name or user.email

    def _conversation_response(
        self,
        doc: OpportunityConversationDocument,
        *,
        viewer_user_id: UUID | None = None,
    ) -> ConversationResponse:
        my_role: Literal["offerer", "interested"] | None = None
        counterpart: str | None = None
        if viewer_user_id is not None:
            if viewer_user_id == doc.offerer_user_id:
                my_role = "offerer"
                counterpart = doc.interested_company_name
            elif viewer_user_id == doc.interested_user_id:
                my_role = "interested"
                counterpart = doc.offerer_company_name
        return ConversationResponse(
            id=doc.id,
            opportunity_id=doc.opportunity_id,
            opportunity_title=doc.opportunity_title,
            offerer_company_id=doc.offerer_company_id,
            offerer_company_name=doc.offerer_company_name,
            offerer_user_id=doc.offerer_user_id,
            interested_company_id=doc.interested_company_id,
            interested_company_name=doc.interested_company_name,
            interested_user_id=doc.interested_user_id,
            created_by_user_id=doc.created_by_user_id,
            status=doc.status,
            last_message_at=doc.last_message_at,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            counterpart_company_name=counterpart,
            my_role=my_role,
        )

    async def _publish(
        self,
        *,
        user_ids: list[UUID] | None = None,
        conversation_id: UUID | None = None,
        to_admins: bool = False,
        event_type: str,
        data: dict[str, object],
    ) -> None:
        if self._realtime is None:
            return
        if user_ids:
            for user_id in user_ids:
                await self._realtime.publish_to_user(user_id, event_type, data)
        if to_admins:
            await self._realtime.publish_to_admins(event_type, data)
        if conversation_id is not None:
            await self._realtime.publish_to_thread(conversation_id, event_type, data)

    def _participant_ids(
        self, conversation: OpportunityConversationDocument
    ) -> list[UUID]:
        ids = {conversation.offerer_user_id, conversation.interested_user_id}
        return list(ids)

    async def _ensure_participant(
        self, conversation_id: UUID, user_id: UUID
    ) -> OpportunityConversationDocument:
        conversation = await self._conversations.get_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        if user_id not in {
            conversation.offerer_user_id,
            conversation.interested_user_id,
        }:
            raise ForbiddenError("You do not have access to this conversation.")
        return conversation

    async def _ensure_open(self, conversation: OpportunityConversationDocument) -> None:
        if conversation.status == ConversationStatus.CLOSED:
            raise ValidationAppError("This conversation is closed.")

    def _author_role_for_user(
        self, conversation: OpportunityConversationDocument, user_id: UUID
    ) -> ConversationAuthorRole:
        if user_id == conversation.offerer_user_id:
            return ConversationAuthorRole.OFFERER
        if user_id == conversation.interested_user_id:
            return ConversationAuthorRole.INTERESTED
        raise ForbiddenError("You do not have access to this conversation.")

    def _company_id_for_user(
        self, conversation: OpportunityConversationDocument, user_id: UUID
    ) -> UUID:
        if user_id == conversation.offerer_user_id:
            return conversation.offerer_company_id
        return conversation.interested_company_id

    # -------------------------------------------------------------- user API
    async def create_or_get(
        self, payload: ConversationCreate, *, firebase_uid: str
    ) -> ConversationResponse:
        user = await self._resolve_user(firebase_uid)
        opportunity = await self._opportunities.get(payload.opportunity_id)
        if opportunity is None or not opportunity.is_active:
            raise NotFoundError("Opportunity not found.")

        company = await self._companies.get(payload.company_id)
        if company is None or not company.is_active:
            raise NotFoundError("Company not found.")
        if company.owner_user_id != user.id:
            raise ForbiddenError("You do not own this company.")
        if company.id == opportunity.company_id:
            raise ValidationAppError(
                "You cannot start a conversation on your own opportunity."
            )

        existing = await self._conversations.get_by_opportunity_and_company(
            opportunity.id, company.id
        )
        if existing is not None:
            return self._conversation_response(existing, viewer_user_id=user.id)

        company_name = _company_display_name(company.legal_name, company.trade_name)
        now = utcnow()
        conversation = OpportunityConversationDocument(
            opportunity_id=opportunity.id,
            opportunity_title=opportunity.title,
            offerer_company_id=opportunity.company_id,
            offerer_company_name=opportunity.company_name,
            offerer_user_id=opportunity.owner_user_id,
            interested_company_id=company.id,
            interested_company_name=company_name,
            interested_user_id=user.id,
            created_by_user_id=user.id,
            status=ConversationStatus.OPEN,
            last_message_at=now if payload.message else None,
        )
        await self._conversations.create(conversation)

        initial_message: OpportunityConversationMessageDocument | None = None
        if payload.message:
            initial_message = OpportunityConversationMessageDocument(
                conversation_id=conversation.id,
                author_id=user.id,
                author_company_id=company.id,
                author_role=ConversationAuthorRole.INTERESTED,
                message_type=ConversationMessageType.PARTICIPANT_MESSAGE,
                body=payload.message,
            )
            await self._messages.create(initial_message)

        starter_name = user.name or user.email or "Usuário"
        event_data: dict[str, object] = {
            "conversation_id": str(conversation.id),
            "opportunity_id": str(conversation.opportunity_id),
            "opportunity_title": conversation.opportunity_title,
        }
        if initial_message is not None:
            msg_response = _message_to_response(
                initial_message, author_name=starter_name
            )
            event_data["message_id"] = str(initial_message.id)
            event_data["message_type"] = initial_message.message_type.value
            event_data["message"] = _message_event_payload(msg_response)

        await self._publish(
            user_ids=self._participant_ids(conversation),
            conversation_id=conversation.id,
            to_admins=True,
            event_type="conversation_created",
            data=event_data,
        )

        offerer = await self._auth.get_by_id(conversation.offerer_user_id)
        if offerer is not None:
            await self._notifications.notify_new_conversation(
                conversation, starter_name=starter_name, recipient=offerer
            )
        await self._notifications.notify_admins_new_conversation(
            conversation, starter_name=starter_name
        )
        return self._conversation_response(conversation, viewer_user_id=user.id)

    async def list_user_conversations(
        self, params: UserConversationListParams, *, firebase_uid: str
    ) -> ConversationListResponse:
        user = await self._resolve_user(firebase_uid)
        skip = (params.page - 1) * params.page_size
        items = await self._conversations.list_for_user(
            user.id, skip=skip, limit=params.page_size, status=params.status
        )
        total = await self._conversations.count_for_user(
            user.id, status=params.status
        )
        responses = [
            self._conversation_response(c, viewer_user_id=user.id) for c in items
        ]
        return ConversationListResponse(
            items=responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_user_conversation(
        self, conversation_id: UUID, *, firebase_uid: str
    ) -> ConversationResponse:
        user = await self._resolve_user(firebase_uid)
        conversation = await self._ensure_participant(conversation_id, user.id)
        return self._conversation_response(conversation, viewer_user_id=user.id)

    async def list_user_messages(
        self, conversation_id: UUID, *, firebase_uid: str
    ) -> ConversationMessageListResponse:
        user = await self._resolve_user(firebase_uid)
        await self._ensure_participant(conversation_id, user.id)
        messages = await self._messages.list_by_conversation(
            conversation_id, user_visible_only=True
        )
        author_ids = list({m.author_id for m in messages})
        users = await self._auth.get_by_ids(author_ids)
        name_map = {u.id: (u.name or u.email) for u in users}
        items = [
            _message_to_response(m, author_name=name_map.get(m.author_id))
            for m in messages
        ]
        return ConversationMessageListResponse(items=items, total=len(items))

    async def add_user_message(
        self,
        conversation_id: UUID,
        payload: ConversationMessageCreate,
        *,
        firebase_uid: str,
    ) -> ConversationMessageResponse:
        user = await self._resolve_user(firebase_uid)
        conversation = await self._ensure_participant(conversation_id, user.id)
        await self._ensure_open(conversation)

        author_role = self._author_role_for_user(conversation, user.id)
        company_id = self._company_id_for_user(conversation, user.id)
        message = OpportunityConversationMessageDocument(
            conversation_id=conversation.id,
            author_id=user.id,
            author_company_id=company_id,
            author_role=author_role,
            message_type=ConversationMessageType.PARTICIPANT_MESSAGE,
            body=payload.body,
        )
        await self._messages.create(message)
        now = utcnow()
        await self._conversations.update(conversation.id, {"last_message_at": now})

        sender_name = user.name or user.email or "Usuário"
        msg_response = _message_to_response(message, author_name=sender_name)
        event_data = {
            "conversation_id": str(conversation.id),
            "opportunity_id": str(conversation.opportunity_id),
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
        }
        await self._publish(
            user_ids=self._participant_ids(conversation),
            conversation_id=conversation.id,
            to_admins=True,
            event_type="message_created",
            data=event_data,
        )

        recipient_id = (
            conversation.offerer_user_id
            if user.id == conversation.interested_user_id
            else conversation.interested_user_id
        )
        recipient = await self._auth.get_by_id(recipient_id)
        if recipient is not None:
            await self._notifications.notify_new_message(
                conversation,
                sender_name=sender_name,
                preview=payload.body,
                recipient=recipient,
            )
        return msg_response

    async def mark_user_messages_read(
        self, conversation_id: UUID, *, firebase_uid: str
    ) -> ConversationMessageListResponse:
        user = await self._resolve_user(firebase_uid)
        conversation = await self._ensure_participant(conversation_id, user.id)
        read_ids = await self._messages.mark_read(
            conversation.id,
            exclude_author_id=user.id,
            message_types=[ConversationMessageType.PARTICIPANT_MESSAGE],
        )
        if read_ids:
            await self._publish(
                user_ids=self._participant_ids(conversation),
                conversation_id=conversation.id,
                to_admins=True,
                event_type="messages_read",
                data={
                    "conversation_id": str(conversation.id),
                    "message_ids": [str(mid) for mid in read_ids],
                    "reader_id": str(user.id),
                },
            )
        return await self.list_user_messages(
            conversation.id, firebase_uid=firebase_uid
        )

    # -------------------------------------------------------------- admin API
    async def list_admin_conversations(
        self, params: AdminConversationListParams
    ) -> ConversationListResponse:
        skip = (params.page - 1) * params.page_size
        items = await self._conversations.list_admin(params, skip=skip)
        total = await self._conversations.count_admin(params)
        responses = [self._conversation_response(c) for c in items]
        return ConversationListResponse(
            items=responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_admin_conversation(
        self, conversation_id: UUID
    ) -> ConversationDetailResponse:
        conversation = await self._conversations.get_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        base = self._conversation_response(conversation)
        offerer_name = await self._user_name(conversation.offerer_user_id)
        interested_name = await self._user_name(conversation.interested_user_id)
        offerer_online = await self._presence.is_online(conversation.offerer_user_id)
        interested_online = await self._presence.is_online(
            conversation.interested_user_id
        )
        return ConversationDetailResponse(
            **base.model_dump(),
            offerer_user_name=offerer_name,
            interested_user_name=interested_name,
            offerer_online=offerer_online,
            interested_online=interested_online,
        )

    async def list_admin_messages(
        self, conversation_id: UUID
    ) -> ConversationMessageListResponse:
        conversation = await self._conversations.get_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        messages = await self._messages.list_by_conversation(
            conversation_id, user_visible_only=False
        )
        author_ids = list({m.author_id for m in messages})
        users = await self._auth.get_by_ids(author_ids)
        name_map = {u.id: (u.name or u.email) for u in users}
        items = [
            _message_to_response(m, author_name=name_map.get(m.author_id))
            for m in messages
        ]
        return ConversationMessageListResponse(items=items, total=len(items))

    async def add_internal_note(
        self,
        conversation_id: UUID,
        payload: ConversationInternalNoteCreate,
        *,
        firebase_uid: str,
    ) -> ConversationMessageResponse:
        admin = await self._resolve_admin(firebase_uid)
        conversation = await self._conversations.get_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")

        message = OpportunityConversationMessageDocument(
            conversation_id=conversation.id,
            author_id=admin.id,
            author_company_id=None,
            author_role=ConversationAuthorRole.ADMIN,
            message_type=ConversationMessageType.INTERNAL_NOTE,
            body=payload.body,
        )
        await self._messages.create(message)

        msg_response = _message_to_response(
            message, author_name=admin.name or admin.email
        )
        event_data = {
            "conversation_id": str(conversation.id),
            "opportunity_id": str(conversation.opportunity_id),
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
        }
        await self._publish(
            conversation_id=conversation.id,
            to_admins=True,
            event_type="message_created",
            data=event_data,
        )
        return msg_response


__all__ = ["ConversationsService"]
