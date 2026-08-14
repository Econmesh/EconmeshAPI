"""Support ticket notification delivery (in-app + email)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.infrastructure.email.client import EmailSender
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.infrastructure.realtime.presence import PresenceService
from src.modules.auth.model import UserDocument
from src.modules.notifications.model import NotificationChannel, NotificationKind
from src.modules.notifications.model import UserNotificationDocument
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.support.model import SupportTicketDocument

if TYPE_CHECKING:
    from src.modules.auth.repository import AuthRepository

logger = get_logger(__name__)


def _format_ticket_label(ticket: SupportTicketDocument) -> str:
    return f"#{ticket.ticket_number:04d}"


class SupportNotificationService:
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
        ticket: SupportTicketDocument,
        event: str,
    ) -> None:
        metadata: dict[str, str] = {
            "ticket_id": str(ticket.id),
            "ticket_number": str(ticket.ticket_number),
            "event": event,
            "source": str(ticket.source),
        }
        doc = UserNotificationDocument(
            user_id=user.id,
            title=title,
            body=body,
            channel=NotificationChannel.IN_APP,
            kind=NotificationKind.SUPPORT,
            metadata=metadata,
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
            )
        except Exception:  # noqa: BLE001
            logger.exception("support_email_failed", user_id=str(user.id))

    async def _notify(
        self,
        user: UserDocument,
        *,
        title: str,
        body: str,
        ticket: SupportTicketDocument,
        event: str,
        action_url: str,
    ) -> None:
        """Online: in-app only. Offline: in-app + email."""
        online = await self._presence.is_online(user.id)
        await self._deliver_in_app(
            user, title=title, body=body, ticket=ticket, event=event
        )
        if not online:
            await self._send_email(
                user, subject=title, body=body, action_url=action_url
            )

    async def _notify_admin_in_app_and_email(
        self,
        admin: UserDocument,
        *,
        title: str,
        body: str,
        ticket: SupportTicketDocument,
        event: str,
        action_url: str,
    ) -> None:
        """Always deliver in-app notification and email (used for external contact)."""
        await self._deliver_in_app(
            admin, title=title, body=body, ticket=ticket, event=event
        )
        await self._send_email(
            admin, subject=title, body=body, action_url=action_url
        )

    async def notify_admins_new_ticket(
        self, ticket: SupportTicketDocument, *, user_name: str
    ) -> None:
        label = _format_ticket_label(ticket)
        title = f"Novo chamado {label}"
        body = f"{user_name} abriu o chamado: {ticket.subject}"
        admins = await self._auth_repo.list_admins()
        admin_url = (
            f"{self._settings.FRONTEND_ADMIN_URL.rstrip('/')}"
            f"/dashboard/suporte/{ticket.id}"
        )
        for admin in admins:
            await self._notify(
                admin,
                title=title,
                body=body,
                ticket=ticket,
                event="ticket_created",
                action_url=admin_url,
            )

    async def notify_admins_external_contact(
        self,
        ticket: SupportTicketDocument,
        *,
        visitor_email: str,
        message_preview: str,
    ) -> None:
        """Notify all admins about a new public-site contact (in-app + email always)."""
        label = _format_ticket_label(ticket)
        title = f"Novo contato do site público {label}"
        body = f"{visitor_email}: {message_preview[:200]}"
        admins = await self._auth_repo.list_admins()
        admin_url = (
            f"{self._settings.FRONTEND_ADMIN_URL.rstrip('/')}"
            f"/dashboard/suporte/{ticket.id}"
        )
        for admin in admins:
            await self._notify_admin_in_app_and_email(
                admin,
                title=title,
                body=body,
                ticket=ticket,
                event="ticket_created",
                action_url=admin_url,
            )

    async def notify_admins_contact_request(
        self,
        ticket: SupportTicketDocument,
        *,
        visitor_name: str,
        visitor_email: str,
        interest_label: str,
    ) -> None:
        """Notify all admins about a DMC/MRI contact request (in-app + email always)."""
        label = _format_ticket_label(ticket)
        title = f"Nova solicitação de contato {label}"
        company = ticket.company or "—"
        body = (
            f"{interest_label}: {visitor_name} ({company}) — {visitor_email}"
        )
        admins = await self._auth_repo.list_admins()
        admin_url = (
            f"{self._settings.FRONTEND_ADMIN_URL.rstrip('/')}"
            f"/dashboard/suporte/{ticket.id}"
        )
        for admin in admins:
            await self._notify_admin_in_app_and_email(
                admin,
                title=title,
                body=body,
                ticket=ticket,
                event="ticket_created",
                action_url=admin_url,
            )

    async def notify_admins_document_review(
        self, ticket: SupportTicketDocument, *, company_name: str
    ) -> None:
        label = _format_ticket_label(ticket)
        title = f"Documentos para análise: {company_name}"
        body = (
            f"A empresa {company_name} enviou documentos para análise "
            f"({label})."
        )
        admins = await self._auth_repo.list_admins()
        admin_url = (
            f"{self._settings.FRONTEND_ADMIN_URL.rstrip('/')}"
            f"/dashboard/suporte/{ticket.id}"
        )
        for admin in admins:
            await self._notify(
                admin,
                title=title,
                body=body,
                ticket=ticket,
                event="document_review",
                action_url=admin_url,
            )

    async def notify_admins_user_message(
        self, ticket: SupportTicketDocument, *, user_name: str, preview: str
    ) -> None:
        label = _format_ticket_label(ticket)
        title = f"Nova mensagem no chamado {label}"
        body = f"{user_name}: {preview[:200]}"
        admins = await self._auth_repo.list_admins()
        admin_url = (
            f"{self._settings.FRONTEND_ADMIN_URL.rstrip('/')}"
            f"/dashboard/suporte/{ticket.id}"
        )
        for admin in admins:
            await self._notify(
                admin,
                title=title,
                body=body,
                ticket=ticket,
                event="message_created",
                action_url=admin_url,
            )

    async def notify_user_admin_reply(
        self, ticket: SupportTicketDocument, user: UserDocument, *, preview: str
    ) -> None:
        label = _format_ticket_label(ticket)
        title = f"Resposta no chamado {label}"
        body = preview[:500]
        app_url = (
            f"{self._settings.FRONTEND_APP_URL.rstrip('/')}"
            f"/dashboard/suporte/{ticket.id}"
        )
        await self._notify(
            user,
            title=title,
            body=body,
            ticket=ticket,
            event="message_created",
            action_url=app_url,
        )

    async def notify_user_ticket_closed(
        self, ticket: SupportTicketDocument, user: UserDocument
    ) -> None:
        label = _format_ticket_label(ticket)
        title = f"Chamado {label} encerrado"
        body = "Seu chamado de suporte foi encerrado pela nossa equipe."
        app_url = (
            f"{self._settings.FRONTEND_APP_URL.rstrip('/')}"
            f"/dashboard/suporte/{ticket.id}"
        )
        await self._notify(
            user,
            title=title,
            body=body,
            ticket=ticket,
            event="ticket_closed",
            action_url=app_url,
        )

    async def notify_visitor_admin_reply(
        self, ticket: SupportTicketDocument, *, email: str, preview: str
    ) -> None:
        label = _format_ticket_label(ticket)
        title = f"Resposta da Econmesh — chamado {label}"
        body = preview[:500]
        try:
            await self._email.send_support_notification(
                to=email,
                subject=title,
                body=body,
                action_url="https://econmesh.com.br",
            )
        except Exception:  # noqa: BLE001
            logger.exception("support_visitor_email_failed", email=email)

    async def notify_visitor_ticket_closed(
        self, ticket: SupportTicketDocument, *, email: str
    ) -> None:
        label = _format_ticket_label(ticket)
        title = f"Chamado {label} encerrado"
        body = "Sua solicitação de contato foi encerrada pela nossa equipe."
        try:
            await self._email.send_support_notification(
                to=email,
                subject=title,
                body=body,
                action_url="https://econmesh.com.br",
            )
        except Exception:  # noqa: BLE001
            logger.exception("support_visitor_email_failed", email=email)


__all__ = ["SupportNotificationService"]
