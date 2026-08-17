"""Company compliance document review queue (support tickets + notifications)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import Settings, get_settings
from src.core.exceptions import NotFoundError, ValidationAppError
from src.core.logging import get_logger
from src.infrastructure.email.client import EmailSender, email_sender
from src.infrastructure.realtime.presence import PresenceService
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.infrastructure.realtime.support_pubsub import SupportRealtimePublisher
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.companies.model import (
    CompanyComplianceFile,
    CompanyDocument,
    ComplianceDocumentStatus,
)
from src.modules.companies.repository import CompaniesRepository
from src.modules.notifications.model import (
    NotificationChannel,
    NotificationKind,
    UserNotificationDocument,
)
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.support.model import (
    SupportAuthorRole,
    SupportMessageDocument,
    SupportMessageType,
    SupportTicketDocument,
    SupportTicketSource,
    SupportTicketStatus,
)
from src.modules.support.notification_service import SupportNotificationService
from src.modules.support.repository import SupportMessagesRepository, SupportTicketsRepository
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

logger = get_logger(__name__)

_KIND_FIELDS = {
    "operating_license": "operating_license",
    "mtr": "mtr_document",
    "signature_authorization": "signature_authorization",
}
_KIND_LABELS = {
    "operating_license": "Licença de operação",
    "mtr": "MTR",
    "signature_authorization": "Autorização de assinatura",
}


def document_field(kind: str) -> str:
    field = _KIND_FIELDS.get(kind)
    if field is None:
        raise ValidationAppError("Unknown document type.", code="invalid_document_kind")
    return field


def document_label(kind: str) -> str:
    return _KIND_LABELS.get(kind, kind)


class ComplianceReviewService:
    def __init__(
        self,
        *,
        companies_repo: CompaniesRepository,
        tickets_repo: SupportTicketsRepository,
        messages_repo: SupportMessagesRepository,
        auth_repo: AuthRepository,
        user_notifications_repo: UserNotificationsRepository,
        email_sender: EmailSender,
        support_notifications: SupportNotificationService,
        support_realtime: SupportRealtimePublisher | None,
        notification_realtime: NotificationRealtimePublisher | None,
        presence: PresenceService,
        settings: Settings | None = None,
    ) -> None:
        self._companies = companies_repo
        self._tickets = tickets_repo
        self._messages = messages_repo
        self._auth = auth_repo
        self._user_notifications = user_notifications_repo
        self._email = email_sender
        self._support_notifications = support_notifications
        self._support_realtime = support_realtime
        self._notification_realtime = notification_realtime
        self._presence = presence
        self._settings = settings or get_settings()

    async def enqueue(
        self, company: CompanyDocument, *, message: str | None = None
    ) -> SupportTicketDocument | None:
        if (
            not company.operating_license
            and not company.mtr_document
            and not company.signature_authorization
        ):
            return None
        now = utcnow()
        body = message or (
            f"A empresa {company.legal_name} enviou documentos para análise."
        )
        open_ticket = await self._tickets.find_open_document_review(company.id)
        if open_ticket is not None:
            updated = await self._tickets.update(
                open_ticket.id, {"last_message_at": now, "updated_at": now}
            )
            ticket = updated or open_ticket
            await self._append_message(ticket, company, body)
            await self._publish_created(ticket, company, body)
            await self._support_notifications.notify_admins_document_review(
                ticket, company_name=company.legal_name
            )
            return ticket

        latest = await self._tickets.find_latest_document_review(company.id)
        if latest is not None and latest.status == SupportTicketStatus.CLOSED:
            updated = await self._tickets.update(
                latest.id,
                {
                    "status": SupportTicketStatus.OPEN.value,
                    "closed_by": None,
                    "closed_at": None,
                    "last_message_at": now,
                    "subject": f"Documentos para análise — {company.legal_name}",
                },
            )
            ticket = updated or latest
            await self._append_message(ticket, company, body)
            await self._publish_created(ticket, company, body)
            await self._support_notifications.notify_admins_document_review(
                ticket, company_name=company.legal_name
            )
            return ticket

        ticket_number = await self._tickets.next_document_review_ticket_number()
        ticket = SupportTicketDocument(
            source=SupportTicketSource.DOCUMENT_REVIEW,
            user_id=company.owner_user_id,
            company_id=company.id,
            company=company.legal_name,
            ticket_number=ticket_number,
            subject=f"Documentos para análise — {company.legal_name}",
            status=SupportTicketStatus.OPEN,
            last_message_at=now,
        )
        await self._tickets.create(ticket)
        await self._append_message(ticket, company, body)
        await self._publish_created(ticket, company, body)
        await self._support_notifications.notify_admins_document_review(
            ticket, company_name=company.legal_name
        )
        return ticket

    async def approve(
        self, company_id: UUID, kind: str, *, reviewer_id: UUID
    ) -> CompanyDocument:
        return await self._review(
            company_id,
            kind,
            reviewer_id=reviewer_id,
            status=ComplianceDocumentStatus.APPROVED,
            reason=None,
        )

    async def reject(
        self, company_id: UUID, kind: str, *, reviewer_id: UUID, reason: str
    ) -> CompanyDocument:
        trimmed = reason.strip()
        if len(trimmed) < 3:
            raise ValidationAppError(
                "Informe o motivo da rejeição.",
                code="rejection_reason_required",
            )
        return await self._review(
            company_id,
            kind,
            reviewer_id=reviewer_id,
            status=ComplianceDocumentStatus.REJECTED,
            reason=trimmed,
        )

    async def _review(
        self,
        company_id: UUID,
        kind: str,
        *,
        reviewer_id: UUID,
        status: ComplianceDocumentStatus,
        reason: str | None,
    ) -> CompanyDocument:
        field = document_field(kind)
        company = await self._companies.get(company_id)
        if company is None or not company.is_active:
            raise NotFoundError("Company not found.")
        current: CompanyComplianceFile | None = getattr(company, field)
        if current is None or not current.storage_key:
            raise NotFoundError("Document not found.", code="document_not_found")
        if current.status != ComplianceDocumentStatus.PENDING:
            raise ValidationAppError(
                "This document has already been reviewed.",
                code="document_already_reviewed",
            )

        reviewed = current.model_copy(
            update={
                "status": status,
                "rejection_reason": reason,
                "reviewed_at": utcnow(),
                "reviewed_by": reviewer_id,
            }
        )
        updated = await self._companies.update(
            company_id, {field: reviewed.model_dump()}
        )
        if updated is None:
            raise NotFoundError("Company not found.")

        await self._notify_owner(updated, kind=kind, status=status, reason=reason)
        await self._maybe_close_ticket(updated)
        return updated

    async def _maybe_close_ticket(self, company: CompanyDocument) -> None:
        required_docs = (company.operating_license, company.mtr_document)
        still_pending = any(
            doc is None or doc.status == ComplianceDocumentStatus.PENDING
            for doc in required_docs
        )
        auth_doc = company.signature_authorization
        if (
            auth_doc is not None
            and auth_doc.status == ComplianceDocumentStatus.PENDING
        ):
            still_pending = True
        if still_pending:
            return
        ticket = await self._tickets.find_open_document_review(company.id)
        if ticket is None:
            return
        now = utcnow()
        await self._tickets.update(
            ticket.id,
            {
                "status": SupportTicketStatus.CLOSED.value,
                "closed_at": now,
                "last_message_at": now,
            },
        )
        if self._support_realtime is not None:
            await self._support_realtime.publish_to_admins(
                "ticket_closed",
                {
                    "ticket_id": str(ticket.id),
                    "ticket_number": ticket.ticket_number,
                    "source": SupportTicketSource.DOCUMENT_REVIEW.value,
                },
            )

    async def _append_message(
        self,
        ticket: SupportTicketDocument,
        company: CompanyDocument,
        body: str,
    ) -> SupportMessageDocument:
        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=company.owner_user_id,
            author_role=SupportAuthorRole.USER,
            message_type=SupportMessageType.USER_MESSAGE,
            body=body,
        )
        await self._messages.create(message)
        return message

    async def _publish_created(
        self,
        ticket: SupportTicketDocument,
        company: CompanyDocument,
        body: str,
    ) -> None:
        if self._support_realtime is None:
            return
        await self._support_realtime.publish_to_admins(
            "ticket_created",
            {
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.ticket_number,
                "source": SupportTicketSource.DOCUMENT_REVIEW.value,
                "company_id": str(company.id),
                "message": {
                    "body": body,
                    "author_name": company.legal_name,
                },
            },
        )

    async def _notify_owner(
        self,
        company: CompanyDocument,
        *,
        kind: str,
        status: ComplianceDocumentStatus,
        reason: str | None,
    ) -> None:
        owner = await self._auth.get_by_id(company.owner_user_id)
        if owner is None:
            return
        label = document_label(kind)
        if status == ComplianceDocumentStatus.APPROVED:
            title = f"{label} aprovado"
            body = f"O documento {label} da empresa {company.legal_name} foi aprovado."
        else:
            title = f"{label} rejeitado"
            body = (
                f"O documento {label} da empresa {company.legal_name} foi rejeitado."
            )
            if reason:
                body = f"{body} Motivo: {reason}"
        await self._deliver_owner_in_app(
            owner,
            title=title,
            body=body,
            company=company,
            kind=kind,
            status=status,
        )
        online = await self._presence.is_online(owner.id)
        if not online and owner.email:
            try:
                await self._email.send_notification(
                    to=owner.email, subject=title, body=body
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "compliance_email_failed", user_id=str(owner.id)
                )

    async def _deliver_owner_in_app(
        self,
        user: UserDocument,
        *,
        title: str,
        body: str,
        company: CompanyDocument,
        kind: str,
        status: ComplianceDocumentStatus,
    ) -> None:
        doc = UserNotificationDocument(
            user_id=user.id,
            title=title,
            body=body,
            channel=NotificationChannel.IN_APP,
            kind=NotificationKind.COMPLIANCE,
            metadata={
                "company_id": str(company.id),
                "document_kind": kind,
                "status": str(status),
                "event": "document_reviewed",
            },
        )
        created = await self._user_notifications.create(doc)
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


def build_compliance_review_service(
    db: AsyncDatabase, redis_client: Redis
) -> ComplianceReviewService:
    auth_repo = AuthRepository(db)
    user_notifications_repo = UserNotificationsRepository(db)
    presence = PresenceService(redis_client)
    notification_realtime = NotificationRealtimePublisher(redis_client)
    support_notifications = SupportNotificationService(
        auth_repo=auth_repo,
        user_notifications_repo=user_notifications_repo,
        email_sender=email_sender,
        notification_realtime=notification_realtime,
        presence=presence,
        settings=get_settings(),
    )
    return ComplianceReviewService(
        companies_repo=CompaniesRepository(db),
        tickets_repo=SupportTicketsRepository(db),
        messages_repo=SupportMessagesRepository(db),
        auth_repo=auth_repo,
        user_notifications_repo=user_notifications_repo,
        email_sender=email_sender,
        support_notifications=support_notifications,
        support_realtime=SupportRealtimePublisher(redis_client),
        notification_realtime=notification_realtime,
        presence=presence,
        settings=get_settings(),
    )


__all__ = [
    "ComplianceReviewService",
    "build_compliance_review_service",
    "document_field",
    "document_label",
]
