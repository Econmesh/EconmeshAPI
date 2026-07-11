"""Agreement notification delivery (in-app + email)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.infrastructure.email.client import EmailSender
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.modules.auth.model import UserDocument
from src.modules.notifications.model import NotificationChannel, NotificationKind
from src.modules.notifications.model import UserNotificationDocument
from src.modules.notifications.repository import UserNotificationsRepository

if TYPE_CHECKING:
    from src.modules.auth.repository import AuthRepository
    from src.modules.agreements.model import AgreementDocument

logger = get_logger(__name__)


class AgreementNotificationService:
    def __init__(
        self,
        *,
        auth_repo: AuthRepository,
        user_notifications_repo: UserNotificationsRepository,
        email_sender: EmailSender,
        notification_realtime: NotificationRealtimePublisher | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._auth_repo = auth_repo
        self._user_notifications_repo = user_notifications_repo
        self._email = email_sender
        self._notification_realtime = notification_realtime
        self._settings = settings or get_settings()

    def _action_url(self, agreement_id: UUID) -> str:
        base = self._settings.FRONTEND_APP_URL.rstrip("/")
        return f"{base}/dashboard/acordos/{agreement_id}"

    async def _deliver(
        self,
        user: UserDocument,
        *,
        title: str,
        body: str,
        agreement_id: UUID,
        event: str,
    ) -> None:
        doc = UserNotificationDocument(
            user_id=user.id,
            title=title,
            body=body,
            channel=NotificationChannel.IN_APP,
            kind=NotificationKind.AGREEMENT,
            metadata={
                "agreement_id": str(agreement_id),
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
        if user.email:
            try:
                await self._email.send_notification(
                    to=user.email,
                    subject=title,
                    body=f"{body}\n\nAcesse: {self._action_url(agreement_id)}",
                )
            except Exception:  # noqa: BLE001
                logger.exception("agreement_email_failed", user_id=str(user.id))

    async def notify_user_ids(
        self,
        user_ids: list[UUID],
        *,
        title: str,
        body: str,
        agreement_id: UUID,
        event: str,
    ) -> None:
        seen: set[UUID] = set()
        for uid in user_ids:
            if uid in seen:
                continue
            seen.add(uid)
            user = await self._auth_repo.get_by_id(uid)
            if user is None or not user.is_active:
                continue
            await self._deliver(
                user,
                title=title,
                body=body,
                agreement_id=agreement_id,
                event=event,
            )

    async def notify_by_emails(
        self,
        emails: list[str],
        *,
        title: str,
        body: str,
        agreement_id: UUID,
        event: str,
    ) -> None:
        for email in emails:
            user = await self._auth_repo.get_by_email(email.lower())
            if user is None:
                # External invitee without account yet — email only
                try:
                    await self._email.send_notification(
                        to=email,
                        subject=title,
                        body=(
                            f"{body}\n\n"
                            "Crie ou entre na sua conta EconMesh para assinar.\n"
                            f"{self._action_url(agreement_id)}"
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("agreement_invite_email_failed", email=email)
                continue
            await self._deliver(
                user,
                title=title,
                body=body,
                agreement_id=agreement_id,
                event=event,
            )

    async def notify_sent(self, agreement: AgreementDocument) -> None:
        emails = [p.email for p in agreement.participants]
        await self.notify_by_emails(
            emails,
            title=f"Novo acordo: {agreement.title}",
            body=f"Você foi convidado a participar do acordo \"{agreement.title}\".",
            agreement_id=agreement.id,
            event="sent",
        )

    async def notify_signed(
        self, agreement: AgreementDocument, *, actor_name: str
    ) -> None:
        user_ids = [agreement.owner_user_id]
        for p in agreement.participants:
            if p.user_id:
                user_ids.append(p.user_id)
        await self.notify_user_ids(
            user_ids,
            title=f"Assinatura em {agreement.title}",
            body=f"{actor_name} concluiu sua etapa no acordo \"{agreement.title}\".",
            agreement_id=agreement.id,
            event="signed",
        )

    async def notify_rejected(
        self, agreement: AgreementDocument, *, actor_name: str, reason: str
    ) -> None:
        await self.notify_user_ids(
            [agreement.owner_user_id],
            title=f"Acordo rejeitado: {agreement.title}",
            body=f"{actor_name} rejeitou o acordo. Motivo: {reason}",
            agreement_id=agreement.id,
            event="rejected",
        )

    async def notify_completed(self, agreement: AgreementDocument) -> None:
        user_ids = [agreement.owner_user_id]
        for p in agreement.participants:
            if p.user_id:
                user_ids.append(p.user_id)
        await self.notify_user_ids(
            user_ids,
            title=f"Acordo concluído: {agreement.title}",
            body=f"O acordo \"{agreement.title}\" foi concluído. Os documentos finais estão disponíveis.",
            agreement_id=agreement.id,
            event="completed",
        )

    async def notify_deadline_soon(self, agreement: AgreementDocument) -> None:
        emails = [
            p.email
            for p in agreement.participants
            if p.status.value in {"pending", "viewed"}
        ]
        await self.notify_by_emails(
            emails,
            title=f"Prazo próximo: {agreement.title}",
            body=f"O acordo \"{agreement.title}\" está próximo do vencimento.",
            agreement_id=agreement.id,
            event="deadline_soon",
        )


__all__ = ["AgreementNotificationService"]
