"""Conversation notification delivery (in-app + email)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.infrastructure.email.client import EmailSender
from src.infrastructure.realtime.presence import PresenceService
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.modules.auth.model import UserDocument
from src.modules.conversations.model import OpportunityConversationDocument
from src.modules.notifications.model import NotificationChannel, NotificationKind
from src.modules.notifications.model import UserNotificationDocument
from src.modules.notifications.repository import UserNotificationsRepository

if TYPE_CHECKING:
    from src.modules.auth.repository import AuthRepository

logger = get_logger(__name__)


class ConversationNotificationService:
    def __init__(
        self,
        *,
        auth_repo: AuthRepository,
        user_notifications_repo: UserNotificationsRepository,
        email_sender: EmailSender,
        notification_realtime: NotificationRealtimePublisher | None,
        presence: PresenceService,
        settings: Settings | None = None,
    ) -> None:
        self._auth_repo = auth_repo
        self._user_notifications_repo = user_notifications_repo
        self._email = email_sender
        self._notification_realtime = notification_realtime
        self._presence = presence
        self._settings = settings or get_settings()

    async def _deliver_in_app(
        self,
        user: UserDocument,
        *,
        title: str,
        body: str,
        conversation: OpportunityConversationDocument,
        event: str,
    ) -> None:
        doc = UserNotificationDocument(
            user_id=user.id,
            title=title,
            body=body,
            channel=NotificationChannel.IN_APP,
            kind=NotificationKind.CONVERSATION,
            metadata={
                "conversation_id": str(conversation.id),
                "opportunity_id": str(conversation.opportunity_id),
                "event": event,
            },
        )
        created = await self._user_notifications_repo.create(doc)
        if self._notification_realtime is not None:
            await self._notification_realtime.publish_user_notification(
                user.id,
                {
                    "id": str(created.id),
                    "title": created.title,
                    "body": created.body,
                    "created_at": created.created_at.isoformat(),
                    "read_at": None,
                    "campaign_id": None,
                    "kind": created.kind,
                    "metadata": created.metadata,
                },
            )

    async def _send_email(
        self,
        user: UserDocument,
        *,
        subject: str,
        body: str,
        action_url: str,
    ) -> None:
        if not user.email:
            return
        try:
            await self._email.send_support_notification(
                to=user.email,
                subject=subject,
                body=body,
                action_url=action_url,
                action_label="Ver conversa",
            )
        except Exception:  # noqa: BLE001
            logger.exception("conversation_email_failed", user_id=str(user.id))

    async def _notify(
        self,
        user: UserDocument,
        *,
        title: str,
        body: str,
        conversation: OpportunityConversationDocument,
        event: str,
        action_url: str,
    ) -> None:
        online = await self._presence.is_online(user.id)
        await self._deliver_in_app(
            user,
            title=title,
            body=body,
            conversation=conversation,
            event=event,
        )
        if not online:
            await self._send_email(
                user, subject=title, body=body, action_url=action_url
            )

    def _app_url(self, conversation: OpportunityConversationDocument) -> str:
        return (
            f"{self._settings.FRONTEND_APP_URL.rstrip('/')}"
            f"/dashboard/conversas/{conversation.id}"
        )

    def _admin_url(self, conversation: OpportunityConversationDocument) -> str:
        return (
            f"{self._settings.FRONTEND_ADMIN_URL.rstrip('/')}"
            f"/dashboard/conversas/{conversation.id}"
        )

    async def notify_new_conversation(
        self,
        conversation: OpportunityConversationDocument,
        *,
        starter_name: str,
        recipient: UserDocument,
    ) -> None:
        title = "Nova conversa sobre oportunidade"
        body = (
            f"{starter_name} iniciou uma conversa sobre "
            f"“{conversation.opportunity_title}”."
        )
        await self._notify(
            recipient,
            title=title,
            body=body,
            conversation=conversation,
            event="conversation_created",
            action_url=self._app_url(conversation),
        )

    async def notify_new_message(
        self,
        conversation: OpportunityConversationDocument,
        *,
        sender_name: str,
        preview: str,
        recipient: UserDocument,
    ) -> None:
        title = f"Nova mensagem: {conversation.opportunity_title}"
        body = f"{sender_name}: {preview[:200]}"
        await self._notify(
            recipient,
            title=title,
            body=body,
            conversation=conversation,
            event="message_created",
            action_url=self._app_url(conversation),
        )

    async def notify_admins_new_conversation(
        self,
        conversation: OpportunityConversationDocument,
        *,
        starter_name: str,
    ) -> None:
        title = "Nova conversa entre empresas"
        body = (
            f"{starter_name} iniciou conversa sobre "
            f"“{conversation.opportunity_title}” "
            f"({conversation.offerer_company_name} × "
            f"{conversation.interested_company_name})."
        )
        admins = await self._auth_repo.list_admins()
        admin_url = self._admin_url(conversation)
        for admin in admins:
            await self._notify(
                admin,
                title=title,
                body=body,
                conversation=conversation,
                event="conversation_created",
                action_url=admin_url,
            )


__all__ = ["ConversationNotificationService"]
