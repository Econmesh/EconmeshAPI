"""Scoped operations for a signed-in DMC agent."""

from __future__ import annotations

from uuid import UUID

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.infrastructure.realtime.support_pubsub import SupportRealtimePublisher
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.companies.model import (
    CompanyAddress,
    CompanyDocument,
    CompanyRegistrationStatus,
)
from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.schema import (
    CompanyAddressResponse,
    PreRegistrationCreate,
    PreRegistrationUpdate,
)
from src.modules.dmc.audit import AuditLog
from src.modules.dmc.model import (
    AuditAction,
    DmcConversationAuthorRole,
    DmcConversationDocument,
    DmcConversationMessageDocument,
    DmcNotificationBatchDocument,
    DmcPortfolioLinkDocument,
    PortfolioSource,
)
from src.modules.dmc.repository import (
    DmcConversationMessagesRepository,
    DmcPortfolioRepository,
    DmcConversationsRepository,
    DmcNotificationBatchesRepository,
)
from src.modules.dmc.schema import (
    DmcCompanyDetail,
    DmcCompanyListResponse,
    DmcCompanyPublic,
    DmcCompanySearchResponse,
    DmcCompanyUser,
    DmcConversationListResponse,
    DmcConversationMessageResponse,
    DmcConversationResponse,
    DmcDashboardResponse,
    DmcIndicator,
    DmcMessageListResponse,
    DmcNotificationBatchResponse,
    DmcNotificationHistoryResponse,
    DmcTicketListResponse,
    DmcTicketSummary,
)
from src.modules.dmc.scope import PortfolioScope, ScopeService
from src.modules.maturity_diagnostics.repository import MaturityDiagnosticsRepository
from src.modules.notifications.model import (
    NotificationChannel,
    NotificationKind,
    UserNotificationDocument,
)
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.opportunities.schema import (
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityResponse,
)
from src.modules.opportunities.service import OpportunitiesService
from src.modules.support.model import (
    SupportAuthorRole,
    SupportContactInterest,
    SupportMessageDocument,
    SupportMessageType,
    SupportTicketDocument,
    SupportTicketStatus,
)
from src.modules.support.notification_service import SupportNotificationService
from src.modules.support.repository import SupportMessagesRepository, SupportTicketsRepository
from src.modules.support.schema import SupportMessageResponse
from src.modules.users.model import UserProfileDocument
from src.shared.utils.time import utcnow


def _preview(body: str, limit: int = 180) -> str:
    text = body.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


class DmcAgentService:
    def __init__(
        self,
        *,
        auth: AuthRepository,
        companies: CompaniesRepository,
        scope: ScopeService,
        conversations: DmcConversationsRepository,
        messages: DmcConversationMessagesRepository,
        batches: DmcNotificationBatchesRepository,
        user_notifications: UserNotificationsRepository,
        tickets: SupportTicketsRepository,
        ticket_messages: SupportMessagesRepository,
        opportunities: OpportunitiesService,
        support_notifications: SupportNotificationService,
        audit: AuditLog,
        portfolio: DmcPortfolioRepository | None = None,
        diagnostics: MaturityDiagnosticsRepository | None = None,
        notification_realtime: NotificationRealtimePublisher | None = None,
        support_realtime: SupportRealtimePublisher | None = None,
    ) -> None:
        self._portfolio = portfolio
        self._diagnostics = diagnostics
        self._auth = auth
        self._companies = companies
        self._scope = scope
        self._conversations = conversations
        self._messages = messages
        self._batches = batches
        self._user_notifications = user_notifications
        self._tickets = tickets
        self._ticket_messages = ticket_messages
        self._opportunities = opportunities
        self._support_notifications = support_notifications
        self._audit = audit
        self._notification_realtime = notification_realtime
        self._support_realtime = support_realtime

    async def _agent(self, firebase_uid: str) -> UserDocument:
        user = await self._auth.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def dashboard(self, firebase_uid: str) -> DmcDashboardResponse:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        registered = sum(
            1 for link in scope.links if link.source == PortfolioSource.REGISTERED
        )
        assigned = sum(
            1 for link in scope.links if link.source == PortfolioSource.ASSIGNED
        )
        pending = await self._tickets.count_for_agent(
            agent.id, status=SupportTicketStatus.OPEN
        )
        in_progress = await self._tickets.count_for_agent(
            agent.id, status=SupportTicketStatus.IN_PROGRESS
        )
        closed = await self._tickets.count_for_agent(
            agent.id, status=SupportTicketStatus.CLOSED
        )
        conversations_pending = await self._conversations.count_pending_for_agent(agent.id)
        recent = await self._tickets.list_recent_for_agent(agent.id, limit=5)
        if self._diagnostics is not None:
            diagnostics_done = await self._diagnostics.count_for_agent(agent.id, open_only=False)
            diagnostics_pending = await self._diagnostics.count_for_agent(agent.id, open_only=True)
        else:
            diagnostics_done = closed
            diagnostics_pending = pending + in_progress
        indicators = [
            DmcIndicator(key="companies_managed", label="Empresas gerenciadas", value=len(scope.links)),
            DmcIndicator(key="companies_registered", label="Empresas cadastradas", value=registered),
            DmcIndicator(key="companies_assigned", label="Empresas em acompanhamento", value=assigned),
            DmcIndicator(key="dmc_requests_pending", label="Solicitações DMC pendentes", value=pending),
            DmcIndicator(
                key="dmc_requests_in_progress",
                label="Solicitações DMC em atendimento",
                value=in_progress,
            ),
            DmcIndicator(
                key="diagnostics_done", label="Diagnósticos realizados", value=diagnostics_done
            ),
            DmcIndicator(
                key="diagnostics_pending",
                label="Diagnósticos em andamento",
                value=diagnostics_pending,
            ),
            DmcIndicator(
                key="conversations_pending",
                label="Conversas pendentes",
                value=conversations_pending,
            ),
        ]
        return DmcDashboardResponse(
            indicators=indicators,
            recent_tickets=[_ticket_summary(ticket) for ticket in recent],
        )

    async def list_companies(self, firebase_uid: str) -> DmcCompanyListResponse:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        owners = await self._owner_names(scope.companies.values())
        items = [
            _company_detail(
                scope.companies[link.company_id],
                in_portfolio=True,
                source=link.source,
                owner_name=owners.get(scope.companies[link.company_id].owner_user_id),
            )
            for link in scope.links
            if link.company_id in scope.companies
        ]
        return DmcCompanyListResponse(items=items, total=len(items))

    async def search_companies(
        self, firebase_uid: str, q: str
    ) -> DmcCompanySearchResponse:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        found = await self._companies.search(q, limit=20, include_pre_registered=True)
        items = [
            _company_public(company, in_portfolio=company.id in scope.company_ids)
            for company in found
        ]
        return DmcCompanySearchResponse(items=items, total=len(items))

    async def get_company(self, firebase_uid: str, company_id: UUID) -> DmcCompanyDetail:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        company = await self._companies.get(company_id)
        if company is None or not company.is_active:
            raise NotFoundError("Company not found.")
        link = next((item for item in scope.links if item.company_id == company_id), None)
        if link is None:
            public = _company_public(company, in_portfolio=False)
            return DmcCompanyDetail(**public.model_dump())
        owners = await self._owner_names([company])
        return _company_detail(
            company,
            in_portfolio=True,
            source=link.source,
            owner_name=owners.get(company.owner_user_id),
        )

    async def pre_register_company(
        self, firebase_uid: str, payload: PreRegistrationCreate
    ) -> DmcCompanyDetail:
        """Create a company without owner/login and add it to the agent portfolio."""
        if self._portfolio is None:
            raise RuntimeError("DmcPortfolioRepository is not configured.")
        agent = await self._agent(firebase_uid)
        existing = await self._companies.get_by_tax_id(payload.country, payload.tax_id)
        if existing is not None:
            raise ConflictError(
                "A company with this tax ID already exists.",
                code="tax_id_exists",
            )

        address = (
            CompanyAddress.model_validate(payload.address.model_dump())
            if payload.address is not None
            else None
        )
        company = await self._companies.create(
            CompanyDocument(
                owner_user_id=None,
                registration_status=CompanyRegistrationStatus.PRE_REGISTERED,
                legal_name=payload.legal_name,
                trade_name=payload.trade_name,
                tax_id=payload.tax_id,
                email=payload.email,
                phone=payload.phone,
                legal_representative=payload.legal_representative,
                address=address,
                country=payload.country,
                website=payload.website,
                description=payload.description,
                sector=payload.sector,
            )
        )
        try:
            await self._portfolio.create(
                DmcPortfolioLinkDocument(
                    agent_user_id=agent.id,
                    company_id=company.id,
                    source=PortfolioSource.REGISTERED,
                    linked_by=agent.id,
                )
            )
        except Exception:
            await self._companies.hard_delete(company.id)
            raise
        await self._audit.record(
            AuditAction.COMPANY_PRE_REGISTERED,
            resource_type="company",
            resource_id=company.id,
            actor_user_id=agent.id,
            after={
                "legal_name": company.legal_name,
                "tax_id": company.tax_id,
                "registration_status": company.registration_status,
            },
        )
        return _company_detail(
            company,
            in_portfolio=True,
            source=PortfolioSource.REGISTERED,
            owner_name=None,
        )

    async def update_pre_registration(
        self, firebase_uid: str, company_id: UUID, payload: PreRegistrationUpdate
    ) -> DmcCompanyDetail:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        company = scope.require_company(company_id)
        if company.registration_status != CompanyRegistrationStatus.PRE_REGISTERED:
            raise ConflictError(
                "Only pre-registered companies can be edited by a DMC agent.",
                code="not_pre_registered",
            )
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            raise ValidationAppError("Nothing to update.", code="empty_update")
        if "legal_name" in patch and patch["legal_name"] is None:
            raise ValidationAppError("legal_name is required.", code="legal_name_required")
        if patch.get("tax_id") and patch["tax_id"] != company.tax_id:
            clash = await self._companies.get_by_tax_id(company.country, patch["tax_id"])
            if clash is not None:
                raise ConflictError(
                    "A company with this tax ID already exists.",
                    code="tax_id_exists",
                )
        elif "tax_id" in patch:
            patch.pop("tax_id")
        if "address" in patch and patch["address"] is not None:
            patch["address"] = CompanyAddress.model_validate(patch["address"]).model_dump()
        updated = await self._companies.update(company_id, patch)
        if updated is None:
            raise NotFoundError("Company not found.")
        await self._audit.record(
            AuditAction.COMPANY_PRE_REGISTRATION_UPDATED,
            resource_type="company",
            resource_id=company_id,
            actor_user_id=agent.id,
            before={key: value for key, value in company.model_dump().items() if key in patch},
            after=patch,
        )
        link = next((item for item in scope.links if item.company_id == company_id), None)
        return _company_detail(
            updated,
            in_portfolio=True,
            source=link.source if link else None,
            owner_name=None,
        )

    async def list_company_users(
        self, firebase_uid: str, company_id: UUID
    ) -> list[DmcCompanyUser]:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        company = scope.require_company(company_id)
        user_ids = [
            user_id
            for user_id, linked_company in scope.user_company.items()
            if linked_company == company.id
        ]
        users = await self._auth.get_by_ids(user_ids)
        profiles = {
            profile.user_id: profile
            for profile in scope.profiles
            if profile.company_id == company.id
        }
        return [
            DmcCompanyUser(
                id=user.id,
                name=user.name,
                email=str(user.email) if user.email else None,
                job_title=_job_title(profiles.get(user.id)),
                company_id=company.id,
            )
            for user in users
            if user.is_active
        ]

    async def list_opportunities(
        self, firebase_uid: str, params: OpportunityListParams
    ) -> OpportunityListResponse:
        await self._agent(firebase_uid)
        return await self._opportunities.list(
            params, firebase_uid=firebase_uid, is_admin=True
        )

    async def get_opportunity(
        self, firebase_uid: str, opportunity_id: UUID
    ) -> OpportunityResponse:
        await self._agent(firebase_uid)
        return await self._opportunities.get(opportunity_id, firebase_uid=firebase_uid)

    async def list_conversations(self, firebase_uid: str) -> DmcConversationListResponse:
        agent = await self._agent(firebase_uid)
        docs = await self._conversations.list_for_agent(agent.id)
        items = await self._conversation_responses(docs)
        return DmcConversationListResponse(items=items, total=len(items))

    async def open_conversation(
        self, firebase_uid: str, *, user_id: UUID, body: str
    ) -> DmcConversationResponse:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        company_id = scope.require_user(user_id)
        existing = await self._conversations.get_pair(agent.id, user_id)
        if existing is None:
            existing = await self._conversations.create(
                DmcConversationDocument(
                    agent_user_id=agent.id,
                    user_id=user_id,
                    company_id=company_id,
                )
            )
        await self._append_message(
            existing,
            author=agent,
            author_role=DmcConversationAuthorRole.DMC_AGENT,
            body=body,
        )
        refreshed = await self._conversations.get(existing.id)
        items = await self._conversation_responses([refreshed or existing])
        return items[0]

    async def list_messages(
        self, firebase_uid: str, conversation_id: UUID
    ) -> DmcMessageListResponse:
        agent = await self._agent(firebase_uid)
        conversation = await self._require_agent_conversation(agent.id, conversation_id)
        return await self._message_list(conversation)

    async def list_user_conversations(
        self, firebase_uid: str
    ) -> DmcConversationListResponse:
        user = await self._agent(firebase_uid)
        docs = await self._conversations.list_for_user(user.id)
        items = await self._conversation_responses(docs)
        return DmcConversationListResponse(items=items, total=len(items))

    async def list_user_messages(
        self, firebase_uid: str, conversation_id: UUID
    ) -> DmcMessageListResponse:
        user = await self._agent(firebase_uid)
        conversation = await self._require_user_conversation(user.id, conversation_id)
        return await self._message_list(conversation)

    async def reply_as_user(
        self, firebase_uid: str, conversation_id: UUID, body: str
    ) -> DmcConversationMessageResponse:
        user = await self._agent(firebase_uid)
        conversation = await self._require_user_conversation(user.id, conversation_id)
        message = await self._append_message(
            conversation,
            author=user,
            author_role=DmcConversationAuthorRole.USER,
            body=body,
        )
        return _message_response(message, author_name=user.name or user.email)

    async def send_message(
        self, firebase_uid: str, conversation_id: UUID, body: str
    ) -> DmcConversationMessageResponse:
        agent = await self._agent(firebase_uid)
        conversation = await self._require_agent_conversation(agent.id, conversation_id)
        scope = await self._scope.for_agent(agent.id)
        scope.require_user(conversation.user_id)
        message = await self._append_message(
            conversation,
            author=agent,
            author_role=DmcConversationAuthorRole.DMC_AGENT,
            body=body,
        )
        return _message_response(message, author_name=agent.name or agent.email)

    async def send_notification(
        self, firebase_uid: str, *, title: str, body: str, user_ids: list[UUID]
    ) -> DmcNotificationBatchResponse:
        agent = await self._agent(firebase_uid)
        scope = await self._scope.for_agent(agent.id)
        unique_ids = list(dict.fromkeys(user_ids))
        outside = [user_id for user_id in unique_ids if user_id not in scope.user_company]
        if outside:
            raise ForbiddenError(
                "Notifications can only be sent to users in your portfolio.",
                code="outside_scope",
            )
        recipients = await self._auth.get_by_ids(unique_ids)
        by_id = {user.id: user for user in recipients}
        missing = [user_id for user_id in unique_ids if user_id not in by_id]
        if missing:
            raise NotFoundError("One or more recipients were not found.")
        created_notes: list[UserNotificationDocument] = []
        for user in recipients:
            note = UserNotificationDocument(
                user_id=user.id,
                title=title.strip(),
                body=body.strip(),
                channel=NotificationChannel.IN_APP,
                kind=NotificationKind.GENERAL,
                metadata={
                    "event": "dmc_notification",
                    "agent_user_id": str(agent.id),
                },
            )
            created = await self._user_notifications.create(note)
            created_notes.append(created)
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
                        "kind": str(created.kind),
                        "metadata": created.metadata,
                    },
                )
        batch = await self._batches.create(
            DmcNotificationBatchDocument(
                agent_user_id=agent.id,
                title=title.strip(),
                body=body.strip(),
                recipient_user_ids=unique_ids,
            )
        )
        await self._audit.record(
            AuditAction.NOTIFICATION_SENT,
            resource_type="dmc_notification_batch",
            resource_id=batch.id,
            actor_user_id=agent.id,
            after={"recipient_user_ids": unique_ids, "title": batch.title},
        )
        return _batch_response(batch)

    async def notification_history(
        self, firebase_uid: str
    ) -> DmcNotificationHistoryResponse:
        agent = await self._agent(firebase_uid)
        docs = await self._batches.list_for_agent(agent.id)
        items = [_batch_response(doc) for doc in docs]
        return DmcNotificationHistoryResponse(items=items, total=len(items))

    async def list_tickets(
        self,
        firebase_uid: str,
        *,
        page: int,
        page_size: int,
        status: SupportTicketStatus | None,
    ) -> DmcTicketListResponse:
        agent = await self._agent(firebase_uid)
        skip = (page - 1) * page_size
        docs = await self._tickets.list_for_agent(
            agent.id, skip=skip, limit=page_size, status=status
        )
        total = await self._tickets.count_for_agent(agent.id, status=status)
        return DmcTicketListResponse(
            items=[_ticket_summary(doc) for doc in docs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_ticket(self, firebase_uid: str, ticket_id: UUID) -> DmcTicketSummary:
        agent = await self._agent(firebase_uid)
        ticket = await self._require_assigned_ticket(agent.id, ticket_id)
        return _ticket_summary(ticket)

    async def list_ticket_messages(
        self, firebase_uid: str, ticket_id: UUID
    ) -> list[SupportMessageResponse]:
        agent = await self._agent(firebase_uid)
        ticket = await self._require_assigned_ticket(agent.id, ticket_id)
        messages = await self._ticket_messages.list_by_ticket(
            ticket.id, user_visible_only=True
        )
        return await self._support_messages(messages, ticket)

    async def reply_ticket(
        self, firebase_uid: str, ticket_id: UUID, body: str
    ) -> SupportMessageResponse:
        agent = await self._agent(firebase_uid)
        ticket = await self._require_assigned_ticket(agent.id, ticket_id)
        if ticket.status == SupportTicketStatus.CLOSED:
            raise ValidationAppError("Ticket is already closed.")
        message = SupportMessageDocument(
            ticket_id=ticket.id,
            author_id=agent.id,
            author_role=SupportAuthorRole.DMC_AGENT,
            message_type=SupportMessageType.AGENT_REPLY,
            body=body.strip(),
        )
        await self._ticket_messages.create(message)
        updates: dict[str, object] = {"last_message_at": utcnow()}
        if ticket.status == SupportTicketStatus.OPEN:
            updates["status"] = SupportTicketStatus.IN_PROGRESS.value
        updated = await self._tickets.update(ticket.id, updates)
        ticket = updated or ticket
        await self._notify_ticket_reply(ticket, body)
        await self._audit.record(
            AuditAction.SUPPORT_REPLIED,
            resource_type="support_ticket",
            resource_id=ticket.id,
            actor_user_id=agent.id,
            after={"message_id": message.id},
        )
        return SupportMessageResponse(
            id=message.id,
            ticket_id=message.ticket_id,
            author_id=message.author_id,
            author_role=message.author_role,
            author_name=agent.name or agent.email,
            message_type=message.message_type,
            body=message.body,
            read_at=message.read_at,
            created_at=message.created_at,
        )

    async def close_ticket(self, firebase_uid: str, ticket_id: UUID) -> DmcTicketSummary:
        agent = await self._agent(firebase_uid)
        ticket = await self._require_assigned_ticket(agent.id, ticket_id)
        if ticket.status == SupportTicketStatus.CLOSED:
            raise ValidationAppError("Ticket is already closed.")
        now = utcnow()
        updated = await self._tickets.update(
            ticket.id,
            {
                "status": SupportTicketStatus.CLOSED.value,
                "closed_by": agent.id,
                "closed_at": now,
            },
        )
        ticket = updated or ticket
        if ticket.user_id is not None:
            owner = await self._auth.get_by_id(ticket.user_id)
            if owner is not None:
                await self._support_notifications.notify_user_ticket_closed(ticket, owner)
        elif ticket.visitor_email:
            await self._support_notifications.notify_visitor_ticket_closed(
                ticket, email=ticket.visitor_email
            )
        await self._audit.record(
            AuditAction.TICKET_CLOSED,
            resource_type="support_ticket",
            resource_id=ticket.id,
            actor_user_id=agent.id,
            before={"status": SupportTicketStatus.OPEN.value},
            after={"status": SupportTicketStatus.CLOSED.value},
        )
        return _ticket_summary(ticket)

    async def _require_user_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> DmcConversationDocument:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def _require_agent_conversation(
        self, agent_user_id: UUID, conversation_id: UUID
    ) -> DmcConversationDocument:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None or conversation.agent_user_id != agent_user_id:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def _require_assigned_ticket(
        self, agent_user_id: UUID, ticket_id: UUID
    ) -> SupportTicketDocument:
        ticket = await self._tickets.get_by_id(ticket_id)
        if (
            ticket is None
            or ticket.interest != SupportContactInterest.DMC
            or ticket.assigned_agent_id != agent_user_id
        ):
            raise NotFoundError("Ticket not found.")
        return ticket

    async def _append_message(
        self,
        conversation: DmcConversationDocument,
        *,
        author: UserDocument,
        author_role: DmcConversationAuthorRole,
        body: str,
    ) -> DmcConversationMessageDocument:
        message = await self._messages.create(
            DmcConversationMessageDocument(
                conversation_id=conversation.id,
                author_id=author.id,
                author_role=author_role,
                body=body.strip(),
            )
        )
        await self._conversations.update(
            conversation.id,
            {
                "last_message_at": message.created_at,
                "last_author_role": author_role.value,
                "last_message_preview": _preview(body),
            },
        )
        await self._audit.record(
            AuditAction.MESSAGE_SENT,
            resource_type="dmc_conversation",
            resource_id=conversation.id,
            actor_user_id=author.id,
            after={"message_id": message.id, "author_role": author_role.value},
        )
        recipient_id = (
            conversation.user_id
            if author_role == DmcConversationAuthorRole.DMC_AGENT
            else conversation.agent_user_id
        )
        await self._notify_conversation(recipient_id, conversation, body)
        return message

    async def _notify_conversation(
        self, recipient_id: UUID, conversation: DmcConversationDocument, body: str
    ) -> None:
        recipient = await self._auth.get_by_id(recipient_id)
        if recipient is None:
            return
        note = UserNotificationDocument(
            user_id=recipient.id,
            title="Nova mensagem do atendimento DMC",
            body=_preview(body),
            channel=NotificationChannel.IN_APP,
            kind=NotificationKind.CONVERSATION,
            metadata={
                "event": "dmc_conversation_message",
                "conversation_id": str(conversation.id),
            },
        )
        created = await self._user_notifications.create(note)
        if self._notification_realtime is not None:
            await self._notification_realtime.publish_user_notification(
                recipient.id,
                {
                    "id": str(created.id),
                    "title": created.title,
                    "body": created.body,
                    "created_at": created.created_at.isoformat(),
                    "read_at": None,
                    "campaign_id": None,
                    "kind": str(created.kind),
                    "metadata": created.metadata,
                },
            )

    async def _notify_ticket_reply(self, ticket: SupportTicketDocument, body: str) -> None:
        if ticket.user_id is not None:
            owner = await self._auth.get_by_id(ticket.user_id)
            if owner is not None:
                await self._support_notifications.notify_user_admin_reply(
                    ticket, owner, preview=body
                )
                return
        if ticket.visitor_email:
            await self._support_notifications.notify_visitor_admin_reply(
                ticket, email=ticket.visitor_email, preview=body
            )

    async def _message_list(
        self, conversation: DmcConversationDocument
    ) -> DmcMessageListResponse:
        docs = await self._messages.list_for_conversation(conversation.id)
        authors = await self._auth.get_by_ids([doc.author_id for doc in docs])
        names = {user.id: (user.name or user.email) for user in authors}
        items = [
            _message_response(doc, author_name=names.get(doc.author_id)) for doc in docs
        ]
        return DmcMessageListResponse(items=items, total=len(items))

    async def _conversation_responses(
        self, docs: list[DmcConversationDocument]
    ) -> list[DmcConversationResponse]:
        user_ids = [doc.user_id for doc in docs]
        company_ids = [doc.company_id for doc in docs]
        users = await self._auth.get_by_ids(user_ids)
        companies = await self._companies.get_many(company_ids)
        user_names = {user.id: (user.name or user.email) for user in users}
        return [
            DmcConversationResponse(
                id=doc.id,
                agent_user_id=doc.agent_user_id,
                user_id=doc.user_id,
                user_name=user_names.get(doc.user_id),
                company_id=doc.company_id,
                company_name=_company_label(companies.get(doc.company_id)),
                last_message_at=doc.last_message_at,
                last_author_role=doc.last_author_role,
                last_message_preview=doc.last_message_preview,
                created_at=doc.created_at,
            )
            for doc in docs
        ]

    async def _owner_names(self, companies: object) -> dict[UUID, str | None]:
        ids = [
            company.owner_user_id  # type: ignore[attr-defined]
            for company in companies  # type: ignore[attr-defined]
            if company.owner_user_id is not None  # type: ignore[attr-defined]
        ]
        users = await self._auth.get_by_ids(ids)
        return {user.id: (user.name or user.email) for user in users}

    async def _support_messages(
        self,
        messages: list[SupportMessageDocument],
        ticket: SupportTicketDocument,
    ) -> list[SupportMessageResponse]:
        authors = await self._auth.get_by_ids(
            [
                message.author_id
                for message in messages
                if message.author_role != SupportAuthorRole.VISITOR
            ]
        )
        names = {user.id: (user.name or user.email) for user in authors}
        items: list[SupportMessageResponse] = []
        for message in messages:
            if message.author_role == SupportAuthorRole.VISITOR:
                author_name = ticket.visitor_name or ticket.visitor_email or "Visitante"
            else:
                author_name = names.get(message.author_id)
            items.append(
                SupportMessageResponse(
                    id=message.id,
                    ticket_id=message.ticket_id,
                    author_id=message.author_id,
                    author_role=message.author_role,
                    author_name=author_name,
                    message_type=message.message_type,
                    body=message.body,
                    read_at=message.read_at,
                    created_at=message.created_at,
                )
            )
        return items


def _company_public(company: CompanyDocument, *, in_portfolio: bool) -> DmcCompanyPublic:
    address = company.address
    return DmcCompanyPublic(
        id=company.id,
        legal_name=company.legal_name,
        trade_name=company.trade_name,
        tax_id=company.tax_id,
        city=address.city if address else None,
        state=address.state if address else None,
        sector=company.sector,
        in_portfolio=in_portfolio,
        registration_status=company.registration_status,
    )


def _company_detail(
    company: CompanyDocument,
    *,
    in_portfolio: bool,
    source: PortfolioSource | None,
    owner_name: str | None,
) -> DmcCompanyDetail:
    public = _company_public(company, in_portfolio=in_portfolio)
    return DmcCompanyDetail(
        **public.model_dump(),
        email=company.email,
        phone=company.phone,
        website=company.website,
        description=company.description,
        legal_representative=company.legal_representative,
        address=(
            CompanyAddressResponse.model_validate(company.address.model_dump())
            if company.address is not None
            else None
        ),
        source=source,
        owner_user_id=company.owner_user_id,
        owner_name=owner_name,
    )


def _company_label(company: CompanyDocument | None) -> str | None:
    if company is None:
        return None
    return company.trade_name or company.legal_name


def _job_title(profile: UserProfileDocument | None) -> str | None:
    if profile is None:
        return None
    return profile.job_title


def _ticket_summary(ticket: SupportTicketDocument) -> DmcTicketSummary:
    return DmcTicketSummary(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        subject=ticket.subject,
        status=ticket.status,
        company=ticket.company,
        visitor_name=ticket.visitor_name,
        visitor_email=ticket.visitor_email,
        phone=ticket.phone,
        position=ticket.position,
        user_id=ticket.user_id,
        company_id=ticket.company_id,
        assigned_agent_id=ticket.assigned_agent_id,
        last_message_at=ticket.last_message_at,
        created_at=ticket.created_at,
    )


def _message_response(
    message: DmcConversationMessageDocument, *, author_name: str | None
) -> DmcConversationMessageResponse:
    return DmcConversationMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        author_id=message.author_id,
        author_role=message.author_role,
        author_name=author_name,
        body=message.body,
        created_at=message.created_at,
    )


def _batch_response(doc: DmcNotificationBatchDocument) -> DmcNotificationBatchResponse:
    return DmcNotificationBatchResponse(
        id=doc.id,
        title=doc.title,
        body=doc.body,
        recipient_user_ids=doc.recipient_user_ids,
        created_at=doc.created_at,
    )


__all__ = ["DmcAgentService"]
