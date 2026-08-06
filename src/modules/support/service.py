"""Business logic for support tickets."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from src.infrastructure.realtime.support_pubsub import SupportRealtimePublisher
from src.modules.auth.model import UserDocument
from src.modules.support.model import (
    VISITOR_AUTHOR_ID,
    VISITOR_TICKET_SOURCES,
    SupportAuthorRole,
    SupportContactInterest,
    SupportMessageDocument,
    SupportMessageType,
    SupportTicketDocument,
    SupportTicketSource,
    SupportTicketStatus,
)
from src.modules.support.notification_service import SupportNotificationService
from src.modules.support.repository import SupportMessagesRepository, SupportTicketsRepository
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

_CONTACT_INTEREST_LABELS = {
    SupportContactInterest.DMC: "Solicitação DMC",
    SupportContactInterest.MRI: "Visita Agente de Circularidade",
}
from src.shared.constants.roles import Role
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from src.infrastructure.realtime.presence import PresenceService
    from src.modules.auth.repository import AuthRepository


def _message_to_response(
    doc: SupportMessageDocument, *, author_name: str | None = None
) -> SupportMessageResponse:
    return SupportMessageResponse(
        id=doc.id,
        ticket_id=doc.ticket_id,
        author_id=doc.author_id,
        author_role=doc.author_role,
        author_name=author_name,
        message_type=doc.message_type,
        body=doc.body,
        read_at=doc.read_at,
        created_at=doc.created_at,
    )


def _subject_from_message(message: str, *, max_len: int = 80) -> str:
    text = message.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}…"


def _is_visitor_ticket(ticket: SupportTicketDocument) -> bool:
    return ticket.source in VISITOR_TICKET_SOURCES


def _contact_request_subject(payload: PublicContactRequestCreate) -> str:
    interest_label = _CONTACT_INTEREST_LABELS[payload.interest]
    return f"{interest_label} — {payload.name} ({payload.company})"


def _contact_request_message_body(payload: PublicContactRequestCreate) -> str:
    interest_label = _CONTACT_INTEREST_LABELS[payload.interest]
    lines = [
        f"Interesse: {interest_label}",
        f"Nome: {payload.name}",
        f"Empresa: {payload.company}",
        f"Cargo: {payload.position}",
        f"E-mail: {payload.email}",
        f"Telefone: {payload.phone}",
    ]
    if payload.address and payload.address.strip():
        lines.append(f"Endereço: {payload.address.strip()}")
    if payload.message and payload.message.strip():
        lines.extend(["", "Mensagem:", payload.message.strip()])
    return "\n".join(lines)


def _message_event_payload(response: SupportMessageResponse) -> dict[str, object]:
    return {
        "id": str(response.id),
        "ticket_id": str(response.ticket_id),
        "author_id": str(response.author_id),
        "author_role": str(response.author_role),
        "author_name": response.author_name,
        "message_type": str(response.message_type),
        "body": response.body,
        "read_at": response.read_at.isoformat() if response.read_at else None,
        "created_at": response.created_at.isoformat(),
    }


class SupportService:
    def __init__(
        self,
        *,
        tickets_repo: SupportTicketsRepository,
        messages_repo: SupportMessagesRepository,
        auth_repo: AuthRepository,
        realtime: SupportRealtimePublisher | None,
        notifications: SupportNotificationService,
        presence: PresenceService,
    ) -> None:
        self._tickets = tickets_repo
        self._messages = messages_repo
        self._auth = auth_repo
        self._realtime = realtime
        self._notifications = notifications
        self._presence = presence

    async def _resolve_user_id(self, firebase_uid: str) -> UUID:
        user = await self._auth.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        return user.id

    async def _resolve_admin(self, firebase_uid: str) -> UserDocument:
        user = await self._auth.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        if user.role != Role.ADMIN:
            raise ForbiddenError("Admin access required.")
        return user

    async def _user_name(self, user_id: UUID) -> str | None:
        user = await self._auth.get_by_id(user_id)
        if user is None:
            return None
        return user.name or user.email

    async def _admin_names(self, *admin_ids: UUID | None) -> dict[UUID, str]:
        ids = [aid for aid in admin_ids if aid is not None]
        if not ids:
            return {}
        users = await self._auth.get_by_ids(ids)
        return {u.id: (u.name or u.email or str(u.id)) for u in users}

    async def _ticket_response(
        self, doc: SupportTicketDocument
    ) -> SupportTicketResponse:
        names = await self._admin_names(
            doc.assigned_admin_id, doc.last_responder_admin_id
        )
        return SupportTicketResponse(
            id=doc.id,
            source=doc.source,
            user_id=doc.user_id,
            visitor_email=doc.visitor_email,
            visitor_name=doc.visitor_name,
            company=doc.company,
            position=doc.position,
            phone=doc.phone,
            address=doc.address,
            interest=doc.interest,
            ticket_number=doc.ticket_number,
            subject=doc.subject,
            status=doc.status,
            assigned_admin_id=doc.assigned_admin_id,
            assigned_admin_name=(
                names.get(doc.assigned_admin_id) if doc.assigned_admin_id else None
            ),
            closed_by=doc.closed_by,
            closed_at=doc.closed_at,
            last_message_at=doc.last_message_at,
            last_responder_admin_id=doc.last_responder_admin_id,
            last_responder_admin_name=(
                names.get(doc.last_responder_admin_id)
                if doc.last_responder_admin_id
                else None
            ),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def _publish(
        self,
        *,
        user_id: UUID | None = None,
        ticket_id: UUID | None = None,
        to_admins: bool = False,
        event_type: str,
        data: dict[str, object],
    ) -> None:
        if self._realtime is None:
            return
        if user_id is not None:
            await self._realtime.publish_to_user(user_id, event_type, data)
        if to_admins:
            await self._realtime.publish_to_admins(event_type, data)
        if ticket_id is not None:
            await self._realtime.publish_to_ticket(ticket_id, event_type, data)

    async def _publish_presence(self, user_id: UUID, *, online: bool) -> None:
        payload = {"user_id": str(user_id), "online": online}
        await self._publish(to_admins=True, event_type="presence_changed", data=payload)

    async def touch_presence(self, *, firebase_uid: str) -> None:
        user_id = await self._resolve_user_id(firebase_uid)
        await self._presence.touch(user_id)
        await self._publish_presence(user_id, online=True)

    async def clear_presence(self, *, firebase_uid: str) -> None:
        user_id = await self._resolve_user_id(firebase_uid)
        await self._presence.clear(user_id)
        await self._publish_presence(user_id, online=False)

    async def _ensure_ticket_owner(
        self, ticket_id: UUID, user_id: UUID
    ) -> SupportTicketDocument:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        if _is_visitor_ticket(ticket):
            raise ForbiddenError("You do not have access to this ticket.")
        if ticket.user_id != user_id:
            raise ForbiddenError("You do not have access to this ticket.")
        return ticket

    async def _ensure_ticket_open(self, ticket: SupportTicketDocument) -> None:
        if ticket.status == SupportTicketStatus.CLOSED:
            raise ValidationAppError("This ticket is closed.")

    # -------------------------------------------------------------- user API
    async def create_ticket(
        self, payload: SupportTicketCreate, *, firebase_uid: str
    ) -> SupportTicketResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        user = await self._auth.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.")

        now = utcnow()
        ticket_number = await self._tickets.next_ticket_number(user_id)
        ticket = SupportTicketDocument(
            source=SupportTicketSource.INTERNAL,
            user_id=user_id,
            ticket_number=ticket_number,
            subject=payload.subject,
            status=SupportTicketStatus.OPEN,
            last_message_at=now,
        )
        await self._tickets.create(ticket)

        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=user_id,
            author_role=SupportAuthorRole.USER,
            message_type=SupportMessageType.USER_MESSAGE,
            body=payload.message,
        )
        await self._messages.create(message)

        msg_response = _message_to_response(
            message, author_name=user.name if user else None
        )
        event_data = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
        }
        await self._publish(
            user_id=user_id,
            ticket_id=ticket.id,
            to_admins=True,
            event_type="ticket_created",
            data=event_data,
        )
        await self._notifications.notify_admins_new_ticket(
            ticket, user_name=user.name or user.email or "Usuário"
        )
        return await self._ticket_response(ticket)

    async def create_external_contact(
        self, payload: ExternalSupportContactCreate
    ) -> SupportTicketResponse:
        now = utcnow()
        ticket_number = await self._tickets.next_external_ticket_number()
        subject = _subject_from_message(payload.message)
        ticket = SupportTicketDocument(
            source=SupportTicketSource.EXTERNAL,
            user_id=None,
            visitor_email=str(payload.email),
            ticket_number=ticket_number,
            subject=subject,
            status=SupportTicketStatus.OPEN,
            last_message_at=now,
        )
        await self._tickets.create(ticket)

        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=VISITOR_AUTHOR_ID,
            author_role=SupportAuthorRole.VISITOR,
            message_type=SupportMessageType.USER_MESSAGE,
            body=payload.message,
        )
        await self._messages.create(message)

        msg_response = _message_to_response(message, author_name=payload.email)
        event_data = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
            "source": SupportTicketSource.EXTERNAL.value,
        }
        await self._publish(
            ticket_id=ticket.id,
            to_admins=True,
            event_type="ticket_created",
            data=event_data,
        )
        await self._notifications.notify_admins_external_contact(
            ticket,
            visitor_email=str(payload.email),
            message_preview=payload.message,
        )
        return await self._ticket_response(ticket)

    async def create_contact_request(
        self, payload: PublicContactRequestCreate
    ) -> SupportTicketResponse:
        now = utcnow()
        ticket_number = await self._tickets.next_contact_request_ticket_number()
        subject = _contact_request_subject(payload)
        body = _contact_request_message_body(payload)
        ticket = SupportTicketDocument(
            source=SupportTicketSource.CONTACT_REQUEST,
            user_id=None,
            visitor_email=str(payload.email),
            visitor_name=payload.name.strip(),
            company=payload.company.strip(),
            position=payload.position.strip(),
            phone=payload.phone.strip(),
            address=payload.address.strip() if payload.address else None,
            interest=payload.interest,
            ticket_number=ticket_number,
            subject=subject,
            status=SupportTicketStatus.OPEN,
            last_message_at=now,
        )
        await self._tickets.create(ticket)

        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=VISITOR_AUTHOR_ID,
            author_role=SupportAuthorRole.VISITOR,
            message_type=SupportMessageType.USER_MESSAGE,
            body=body,
        )
        await self._messages.create(message)

        author_name = payload.name.strip() or str(payload.email)
        msg_response = _message_to_response(message, author_name=author_name)
        event_data = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
            "source": SupportTicketSource.CONTACT_REQUEST.value,
        }
        await self._publish(
            ticket_id=ticket.id,
            to_admins=True,
            event_type="ticket_created",
            data=event_data,
        )
        await self._notifications.notify_admins_contact_request(
            ticket,
            visitor_name=payload.name.strip(),
            visitor_email=str(payload.email),
            interest_label=_CONTACT_INTEREST_LABELS[payload.interest],
        )
        return await self._ticket_response(ticket)

    async def list_user_tickets(
        self, params: UserSupportTicketListParams, *, firebase_uid: str
    ) -> SupportTicketListResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        skip = (params.page - 1) * params.page_size
        items = await self._tickets.list_by_user(
            user_id, skip=skip, limit=params.page_size, status=params.status
        )
        total = await self._tickets.count_by_user(user_id, status=params.status)
        responses = [await self._ticket_response(t) for t in items]
        return SupportTicketListResponse(
            items=responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_user_ticket(
        self, ticket_id: UUID, *, firebase_uid: str
    ) -> SupportTicketResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        ticket = await self._ensure_ticket_owner(ticket_id, user_id)
        return await self._ticket_response(ticket)

    async def list_user_messages(
        self, ticket_id: UUID, *, firebase_uid: str
    ) -> SupportMessageListResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        await self._ensure_ticket_owner(ticket_id, user_id)
        messages = await self._messages.list_by_ticket(
            ticket_id, user_visible_only=True
        )
        author_ids = list({m.author_id for m in messages})
        users = await self._auth.get_by_ids(author_ids)
        name_map = {u.id: (u.name or u.email) for u in users}
        items = [
            _message_to_response(m, author_name=name_map.get(m.author_id))
            for m in messages
        ]
        return SupportMessageListResponse(items=items, total=len(items))

    async def add_user_message(
        self, ticket_id: UUID, payload: SupportMessageCreate, *, firebase_uid: str
    ) -> SupportMessageResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        user = await self._auth.get_by_id(user_id)
        ticket = await self._ensure_ticket_owner(ticket_id, user_id)
        await self._ensure_ticket_open(ticket)

        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=user_id,
            author_role=SupportAuthorRole.USER,
            message_type=SupportMessageType.USER_MESSAGE,
            body=payload.body,
        )
        await self._messages.create(message)
        now = utcnow()
        await self._tickets.update(
            ticket.id, {"last_message_at": now}
        )

        msg_response = _message_to_response(
            message, author_name=user.name if user else None
        )
        event_data = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
        }
        await self._publish(
            user_id=user_id,
            ticket_id=ticket.id,
            to_admins=True,
            event_type="message_created",
            data=event_data,
        )
        if user is not None:
            await self._notifications.notify_admins_user_message(
                ticket,
                user_name=user.name or user.email or "Usuário",
                preview=payload.body,
            )
        return _message_to_response(
            message, author_name=user.name if user else None
        )

    async def mark_user_messages_read(
        self, ticket_id: UUID, *, firebase_uid: str
    ) -> SupportMessageListResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        ticket = await self._ensure_ticket_owner(ticket_id, user_id)
        read_ids = await self._messages.mark_read(
            ticket.id,
            message_types=[SupportMessageType.ADMIN_REPLY],
        )
        if read_ids:
            await self._publish(
                ticket_id=ticket.id,
                to_admins=True,
                event_type="messages_read",
                data={
                    "ticket_id": str(ticket.id),
                    "message_ids": [str(mid) for mid in read_ids],
                    "reader": "user",
                },
            )
        return await self.list_user_messages(ticket.id, firebase_uid=firebase_uid)

    async def mark_admin_messages_read(self, ticket_id: UUID) -> SupportMessageListResponse:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        read_ids = await self._messages.mark_read(
            ticket.id,
            message_types=[SupportMessageType.USER_MESSAGE],
        )
        if read_ids:
            publish_kwargs: dict[str, object] = {
                "ticket_id": ticket.id,
                "to_admins": True,
                "event_type": "messages_read",
                "data": {
                    "ticket_id": str(ticket.id),
                    "message_ids": [str(mid) for mid in read_ids],
                    "reader": "admin",
                },
            }
            if ticket.user_id is not None:
                publish_kwargs["user_id"] = ticket.user_id
            await self._publish(**publish_kwargs)  # type: ignore[arg-type]
        return await self.list_admin_messages(ticket.id)

    # -------------------------------------------------------------- admin API
    async def list_admin_tickets(
        self, params: AdminSupportTicketListParams
    ) -> SupportTicketListResponse:
        skip = (params.page - 1) * params.page_size
        items = await self._tickets.list_admin(params, skip=skip)
        total = await self._tickets.count_admin(params)
        responses = [await self._ticket_response(t) for t in items]
        return SupportTicketListResponse(
            items=responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_admin_ticket(self, ticket_id: UUID) -> SupportTicketDetailResponse:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        base = await self._ticket_response(ticket)
        if _is_visitor_ticket(ticket):
            if ticket.source == SupportTicketSource.CONTACT_REQUEST:
                user_name = ticket.visitor_name or "Solicitação de contato"
            else:
                user_name = "Visitante (site)"
            return SupportTicketDetailResponse(
                **base.model_dump(),
                user_name=user_name,
                user_email=ticket.visitor_email,
                user_online=False,
            )
        owner = await self._auth.get_by_id(ticket.user_id) if ticket.user_id else None
        user_online = (
            await self._presence.is_online(ticket.user_id)
            if ticket.user_id is not None
            else False
        )
        return SupportTicketDetailResponse(
            **base.model_dump(),
            user_name=owner.name if owner else None,
            user_email=owner.email if owner else None,
            user_online=user_online,
        )

    async def list_admin_messages(self, ticket_id: UUID) -> SupportMessageListResponse:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        messages = await self._messages.list_by_ticket(ticket_id, user_visible_only=False)
        items = await self._resolve_message_author_names(messages, ticket)
        return SupportMessageListResponse(items=items, total=len(items))

    async def _resolve_message_author_names(
        self,
        messages: list[SupportMessageDocument],
        ticket: SupportTicketDocument,
    ) -> list[SupportMessageResponse]:
        author_ids = [
            m.author_id
            for m in messages
            if m.author_role != SupportAuthorRole.VISITOR
        ]
        users = await self._auth.get_by_ids(author_ids)
        name_map = {u.id: (u.name or u.email) for u in users}
        items: list[SupportMessageResponse] = []
        for message in messages:
            if message.author_role == SupportAuthorRole.VISITOR:
                items.append(
                    _message_to_response(
                        message,
                        author_name=(
                            ticket.visitor_name
                            or ticket.visitor_email
                            or "Visitante"
                        ),
                    )
                )
            else:
                items.append(
                    _message_to_response(
                        message, author_name=name_map.get(message.author_id)
                    )
                )
        return items

    async def add_admin_reply(
        self, ticket_id: UUID, payload: SupportMessageCreate, *, firebase_uid: str
    ) -> SupportMessageResponse:
        admin = await self._resolve_admin(firebase_uid)
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        await self._ensure_ticket_open(ticket)

        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=admin.id,
            author_role=SupportAuthorRole.ADMIN,
            message_type=SupportMessageType.ADMIN_REPLY,
            body=payload.body,
        )
        await self._messages.create(message)
        now = utcnow()
        updates: dict[str, object] = {
            "last_message_at": now,
            "last_responder_admin_id": admin.id,
        }
        if ticket.status == SupportTicketStatus.OPEN:
            updates["status"] = SupportTicketStatus.IN_PROGRESS.value
        if ticket.assigned_admin_id is None:
            updates["assigned_admin_id"] = admin.id
        updated = await self._tickets.update(ticket.id, updates)
        ticket = updated or ticket

        msg_response = _message_to_response(
            message, author_name=admin.name or admin.email
        )
        event_data = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
        }
        await self._publish(
            user_id=ticket.user_id if ticket.user_id is not None else None,
            ticket_id=ticket.id,
            to_admins=True,
            event_type="message_created",
            data=event_data,
        )
        if _is_visitor_ticket(ticket) and ticket.visitor_email:
            await self._notifications.notify_visitor_admin_reply(
                ticket, email=ticket.visitor_email, preview=payload.body
            )
        else:
            owner = await self._auth.get_by_id(ticket.user_id) if ticket.user_id else None
            if owner is not None:
                await self._notifications.notify_user_admin_reply(
                    ticket, owner, preview=payload.body
                )
        return _message_to_response(
            message, author_name=admin.name or admin.email
        )

    async def add_internal_note(
        self, ticket_id: UUID, payload: SupportInternalNoteCreate, *, firebase_uid: str
    ) -> SupportMessageResponse:
        admin = await self._resolve_admin(firebase_uid)
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")

        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=admin.id,
            author_role=SupportAuthorRole.ADMIN,
            message_type=SupportMessageType.INTERNAL_NOTE,
            body=payload.body,
        )
        await self._messages.create(message)

        msg_response = _message_to_response(
            message, author_name=admin.name or admin.email
        )
        event_data = {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "message_id": str(message.id),
            "message_type": message.message_type.value,
            "message": _message_event_payload(msg_response),
        }
        await self._publish(
            ticket_id=ticket.id,
            to_admins=True,
            event_type="message_created",
            data=event_data,
        )
        return _message_to_response(
            message, author_name=admin.name or admin.email
        )

    async def assign_ticket(
        self, ticket_id: UUID, payload: SupportTicketAssign, *, firebase_uid: str
    ) -> SupportTicketResponse:
        admin = await self._resolve_admin(firebase_uid)
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")

        assignee_id = payload.admin_id or admin.id
        if payload.admin_id is not None:
            assignee = await self._auth.get_by_id(payload.admin_id)
            if assignee is None or assignee.role != Role.ADMIN:
                raise ValidationAppError("Invalid admin id.")

        updated = await self._tickets.update(
            ticket.id, {"assigned_admin_id": assignee_id}
        )
        ticket = updated or ticket
        await self._publish(
            ticket_id=ticket.id,
            to_admins=True,
            event_type="ticket_assigned",
            data={
                "ticket_id": str(ticket.id),
                "assigned_admin_id": str(assignee_id),
            },
        )
        return await self._ticket_response(ticket)

    async def close_ticket(
        self, ticket_id: UUID, *, firebase_uid: str
    ) -> SupportTicketResponse:
        admin = await self._resolve_admin(firebase_uid)
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        if ticket.status == SupportTicketStatus.CLOSED:
            raise ValidationAppError("Ticket is already closed.")

        now = utcnow()
        updated = await self._tickets.update(
            ticket.id,
            {
                "status": SupportTicketStatus.CLOSED.value,
                "closed_by": admin.id,
                "closed_at": now,
            },
        )
        ticket = updated or ticket

        publish_kwargs: dict[str, object] = {
            "ticket_id": ticket.id,
            "to_admins": True,
            "event_type": "ticket_closed",
            "data": {
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.ticket_number,
            },
        }
        if ticket.user_id is not None:
            publish_kwargs["user_id"] = ticket.user_id
        await self._publish(**publish_kwargs)  # type: ignore[arg-type]
        if _is_visitor_ticket(ticket) and ticket.visitor_email:
            await self._notifications.notify_visitor_ticket_closed(
                ticket, email=ticket.visitor_email
            )
        else:
            owner = await self._auth.get_by_id(ticket.user_id) if ticket.user_id else None
            if owner is not None:
                await self._notifications.notify_user_ticket_closed(ticket, owner)
        return await self._ticket_response(ticket)

    async def reopen_ticket(
        self, ticket_id: UUID, *, firebase_uid: str
    ) -> SupportTicketResponse:
        await self._resolve_admin(firebase_uid)
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        if ticket.status != SupportTicketStatus.CLOSED:
            raise ValidationAppError("Only closed tickets can be reopened.")

        updated = await self._tickets.update(
            ticket.id,
            {
                "status": SupportTicketStatus.IN_PROGRESS.value,
                "closed_by": None,
                "closed_at": None,
            },
        )
        ticket = updated or ticket
        publish_kwargs: dict[str, object] = {
            "ticket_id": ticket.id,
            "to_admins": True,
            "event_type": "ticket_reopened",
            "data": {
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.ticket_number,
            },
        }
        if ticket.user_id is not None:
            publish_kwargs["user_id"] = ticket.user_id
        await self._publish(**publish_kwargs)  # type: ignore[arg-type]
        return await self._ticket_response(ticket)


__all__ = ["SupportService"]
