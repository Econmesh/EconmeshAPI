"""Administrator controls for DMC agents, queue and portfolio."""

from __future__ import annotations

from uuid import UUID

from src.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.dmc.agent_service import _company_detail, _ticket_summary
from src.modules.dmc.assignment import DmcAssignmentService
from src.modules.dmc.audit import AuditLog
from src.modules.dmc.model import (
    AuditAction,
    DmcAgentDocument,
    DmcPortfolioLinkDocument,
    PortfolioSource,
)
from src.modules.dmc.queue import next_in_queue
from src.modules.dmc.repository import AuditEventsRepository, DmcAgentsRepository, DmcPortfolioRepository
from src.modules.dmc.schema import (
    AuditEventListResponse,
    AuditEventResponse,
    DmcAgentDetailResponse,
    DmcCompanyDetail,
    DmcQueueAgent,
    DmcQueueResponse,
    DmcTicketListResponse,
)
from src.modules.dmc.scope import ScopeService
from src.modules.platform_settings.model import DmcAssignmentMode
from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.modules.support.model import SupportTicketStatus
from src.modules.support.repository import SupportTicketsRepository
from src.shared.constants.roles import Role


class DmcAdminService:
    def __init__(
        self,
        *,
        agents: DmcAgentsRepository,
        portfolio: DmcPortfolioRepository,
        auth: AuthRepository,
        companies: CompaniesRepository,
        tickets: SupportTicketsRepository,
        settings: PlatformSettingsRepository,
        assignment: DmcAssignmentService,
        scope: ScopeService,
        audit: AuditLog,
        audit_events: AuditEventsRepository,
    ) -> None:
        self._agents = agents
        self._portfolio = portfolio
        self._auth = auth
        self._companies = companies
        self._tickets = tickets
        self._settings = settings
        self._assignment = assignment
        self._scope = scope
        self._audit = audit
        self._audit_events = audit_events

    async def queue(self) -> DmcQueueResponse:
        settings = await self._settings.get_or_create()
        rows = await self._queue_rows()
        candidate = next_in_queue(await self._assignment.candidates())
        return DmcQueueResponse(
            mode=settings.dmc_assignment_mode,
            next_agent_user_id=candidate.user_id if candidate else None,
            agents=rows,
        )

    async def set_mode(
        self, mode: DmcAssignmentMode, *, actor_firebase_uid: str
    ) -> DmcQueueResponse:
        actor = await self._actor(actor_firebase_uid)
        current = await self._settings.get_or_create()
        previous = current.dmc_assignment_mode
        await self._settings.update({"dmc_assignment_mode": mode.value})
        await self._audit.record(
            AuditAction.ASSIGNMENT_MODE_CHANGED,
            resource_type="platform_settings",
            resource_id=current.id,
            actor_user_id=actor.id,
            before={"dmc_assignment_mode": previous},
            after={"dmc_assignment_mode": mode},
        )
        return await self.queue()

    async def reorder(self, agent_user_ids: list[UUID], *, actor_firebase_uid: str) -> DmcQueueResponse:
        actor = await self._actor(actor_firebase_uid)
        existing = await self._agents.list_ordered()
        existing_ids = [agent.user_id for agent in existing]
        if sorted(existing_ids, key=str) != sorted(agent_user_ids, key=str):
            raise ValidationAppError("Queue reorder must include every DMC agent exactly once.")
        before = [str(user_id) for user_id in existing_ids]
        for position, user_id in enumerate(agent_user_ids):
            await self._agents.update(user_id, {"queue_position": position})
        await self._audit.record(
            AuditAction.QUEUE_REORDERED,
            resource_type="dmc_queue",
            actor_user_id=actor.id,
            before={"order": before},
            after={"order": [str(user_id) for user_id in agent_user_ids]},
        )
        return await self.queue()

    async def set_availability(
        self, agent_user_id: UUID, *, available: bool, actor_firebase_uid: str
    ) -> DmcQueueAgent:
        actor = await self._actor(actor_firebase_uid)
        agent_user = await self._require_agent_user(agent_user_id)
        current = await self._agents.get_by_user_id(agent_user_id)
        if current is None:
            raise NotFoundError("DMC agent not found.")
        updated = await self._agents.update(agent_user_id, {"available": available})
        await self._audit.record(
            AuditAction.AGENT_AVAILABILITY_CHANGED,
            resource_type="dmc_agent",
            resource_id=agent_user_id,
            actor_user_id=actor.id,
            before={"available": current.available},
            after={"available": available},
        )
        rows = await self._queue_rows()
        match = next((row for row in rows if row.user_id == agent_user.id), None)
        if match is None and updated is not None:
            return DmcQueueAgent(
                user_id=agent_user.id,
                name=agent_user.name,
                email=str(agent_user.email) if agent_user.email else None,
                is_active=agent_user.is_active,
                available=updated.available,
                queue_position=updated.queue_position,
                last_assigned_at=updated.last_assigned_at,
            )
        if match is None:
            raise NotFoundError("DMC agent not found.")
        return match

    async def get_agent(self, agent_user_id: UUID) -> DmcAgentDetailResponse:
        agent_user = await self._require_agent_user(agent_user_id)
        agent_doc = await self._agents.get_by_user_id(agent_user_id)
        if agent_doc is None:
            raise NotFoundError("DMC agent not found.")
        scope = await self._scope.for_agent(agent_user_id)
        owners = await self._auth.get_by_ids(
            [company.owner_user_id for company in scope.companies.values()]
        )
        owner_names = {user.id: (user.name or user.email) for user in owners}
        companies = [
            _company_detail(
                scope.companies[link.company_id],
                in_portfolio=True,
                source=link.source,
                owner_name=owner_names.get(scope.companies[link.company_id].owner_user_id),
            )
            for link in scope.links
            if link.company_id in scope.companies
        ]
        open_count = await self._tickets.count_for_agent(
            agent_user_id, status=SupportTicketStatus.OPEN
        )
        in_progress = await self._tickets.count_for_agent(
            agent_user_id, status=SupportTicketStatus.IN_PROGRESS
        )
        return DmcAgentDetailResponse(
            user_id=agent_user.id,
            name=agent_user.name,
            email=str(agent_user.email) if agent_user.email else None,
            is_active=agent_user.is_active,
            available=agent_doc.available,
            queue_position=agent_doc.queue_position,
            companies=companies,
            open_count=open_count,
            in_progress_count=in_progress,
            last_assigned_at=agent_doc.last_assigned_at,
        )

    async def link_company(
        self,
        agent_user_id: UUID,
        company_id: UUID,
        source: PortfolioSource,
        *,
        actor_firebase_uid: str,
    ) -> DmcCompanyDetail:
        actor = await self._actor(actor_firebase_uid)
        await self._require_agent_user(agent_user_id)
        company = await self._companies.get(company_id)
        if company is None or not company.is_active:
            raise NotFoundError("Company not found.")
        existing = await self._portfolio.get_link(agent_user_id, company_id)
        if existing is not None:
            raise ConflictError("Company is already linked to this agent.")
        await self._portfolio.create(
            DmcPortfolioLinkDocument(
                agent_user_id=agent_user_id,
                company_id=company_id,
                source=source,
                linked_by=actor.id,
            )
        )
        await self._audit.record(
            AuditAction.PORTFOLIO_LINKED,
            resource_type="dmc_portfolio",
            resource_id=company_id,
            actor_user_id=actor.id,
            after={"agent_user_id": agent_user_id, "source": source},
        )
        owner = await self._auth.get_by_id(company.owner_user_id)
        return _company_detail(
            company,
            in_portfolio=True,
            source=source,
            owner_name=(owner.name or owner.email) if owner else None,
        )

    async def unlink_company(
        self, agent_user_id: UUID, company_id: UUID, *, actor_firebase_uid: str
    ) -> None:
        actor = await self._actor(actor_firebase_uid)
        existing = await self._portfolio.get_link(agent_user_id, company_id)
        if existing is None:
            raise NotFoundError("Portfolio link not found.")
        await self._portfolio.delete(agent_user_id, company_id)
        await self._audit.record(
            AuditAction.PORTFOLIO_UNLINKED,
            resource_type="dmc_portfolio",
            resource_id=company_id,
            actor_user_id=actor.id,
            before={"agent_user_id": agent_user_id, "source": existing.source},
        )

    async def list_agent_tickets(
        self, agent_user_id: UUID, *, page: int, page_size: int
    ) -> DmcTicketListResponse:
        await self._require_agent_user(agent_user_id)
        skip = (page - 1) * page_size
        docs = await self._tickets.list_for_agent(agent_user_id, skip=skip, limit=page_size)
        total = await self._tickets.count_for_agent(agent_user_id)
        return DmcTicketListResponse(
            items=[_ticket_summary(doc) for doc in docs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def assign_ticket(
        self, ticket_id: UUID, agent_user_id: UUID, *, actor_firebase_uid: str
    ) -> DmcTicketListResponse:
        actor = await self._actor(actor_firebase_uid)
        await self._assignment.assign(
            ticket_id,
            agent_user_id=agent_user_id,
            mode="manual",
            actor_user_id=actor.id,
        )
        return await self.list_agent_tickets(agent_user_id, page=1, page_size=20)

    async def audit_log(self, *, limit: int = 100) -> AuditEventListResponse:
        docs = await self._audit_events.list_recent(limit=limit)
        items = [
            AuditEventResponse(
                id=doc.id,
                actor_user_id=doc.actor_user_id,
                action=doc.action,
                resource_type=doc.resource_type,
                resource_id=doc.resource_id,
                before=doc.before,
                after=doc.after,
                created_at=doc.created_at,
            )
            for doc in docs
        ]
        return AuditEventListResponse(items=items, total=len(items))

    async def ensure_profile(
        self,
        user: UserDocument,
        *,
        actor_user_id: UUID | None,
        previous_role: Role | None,
        previous_active: bool | None,
    ) -> None:
        """Create or update the DMC agent record when an admin changes the user."""
        if user.role == Role.DMC_AGENT:
            existing = await self._agents.get_by_user_id(user.id)
            if existing is None:
                position = await self._agents.next_queue_position()
                await self._agents.create(
                    DmcAgentDocument(
                        user_id=user.id,
                        available=True,
                        queue_position=position,
                        created_by=actor_user_id,
                    )
                )
                await self._audit.record(
                    AuditAction.AGENT_CREATED,
                    resource_type="dmc_agent",
                    resource_id=user.id,
                    actor_user_id=actor_user_id,
                    after={"role": Role.DMC_AGENT.value, "available": True},
                )
            elif previous_role is not None and previous_role != Role.DMC_AGENT:
                await self._audit.record(
                    AuditAction.AGENT_ROLE_CHANGED,
                    resource_type="dmc_agent",
                    resource_id=user.id,
                    actor_user_id=actor_user_id,
                    before={"role": previous_role.value},
                    after={"role": Role.DMC_AGENT.value},
                )
        elif previous_role == Role.DMC_AGENT:
            await self._agents.update(user.id, {"available": False})
            await self._audit.record(
                AuditAction.AGENT_ROLE_CHANGED,
                resource_type="dmc_agent",
                resource_id=user.id,
                actor_user_id=actor_user_id,
                before={"role": Role.DMC_AGENT.value},
                after={"role": user.role.value, "available": False},
            )

        if user.role == Role.DMC_AGENT and previous_active is not None and previous_active != user.is_active:
            await self._audit.record(
                AuditAction.AGENT_ACTIVATED if user.is_active else AuditAction.AGENT_DEACTIVATED,
                resource_type="dmc_agent",
                resource_id=user.id,
                actor_user_id=actor_user_id,
                before={"is_active": previous_active},
                after={"is_active": user.is_active},
            )

    async def _queue_rows(self) -> list[DmcQueueAgent]:
        agents = await self._agents.list_ordered()
        users = await self._auth.get_by_ids([agent.user_id for agent in agents])
        by_id = {user.id: user for user in users}
        rows: list[DmcQueueAgent] = []
        for agent in agents:
            user = by_id.get(agent.user_id)
            if user is None or user.role != Role.DMC_AGENT:
                continue
            open_count = await self._tickets.count_for_agent(
                agent.user_id, status=SupportTicketStatus.OPEN
            )
            in_progress = await self._tickets.count_for_agent(
                agent.user_id, status=SupportTicketStatus.IN_PROGRESS
            )
            rows.append(
                DmcQueueAgent(
                    user_id=user.id,
                    name=user.name,
                    email=str(user.email) if user.email else None,
                    is_active=user.is_active,
                    available=agent.available,
                    queue_position=agent.queue_position,
                    open_count=open_count,
                    in_progress_count=in_progress,
                    last_assigned_at=agent.last_assigned_at,
                )
            )
        return rows

    async def _require_agent_user(self, user_id: UUID) -> UserDocument:
        user = await self._auth.get_by_id(user_id)
        if user is None or user.role != Role.DMC_AGENT:
            raise NotFoundError("DMC agent not found.")
        return user

    async def _actor(self, firebase_uid: str) -> UserDocument:
        user = await self._auth.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        return user


__all__ = ["DmcAdminService"]
