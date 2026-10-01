"""Manual and round-robin assignment of DMC contact requests."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from src.core.exceptions import NotFoundError, ValidationAppError
from src.modules.auth.repository import AuthRepository
from src.modules.dmc.audit import AuditLog
from src.modules.dmc.model import AuditAction
from src.modules.dmc.queue import QueueCandidate, next_in_queue
from src.modules.dmc.repository import DmcAgentsRepository
from src.modules.platform_settings.model import DmcAssignmentMode
from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.modules.support.model import (
    SupportContactInterest,
    SupportTicketDocument,
)
from src.modules.support.notification_service import SupportNotificationService
from src.modules.support.repository import SupportTicketsRepository
from src.shared.constants.roles import Role
from src.shared.utils.time import utcnow

AssignmentMode = Literal["manual", "automatic"]


class DmcAssignmentService:
    def __init__(
        self,
        *,
        agents: DmcAgentsRepository,
        auth: AuthRepository,
        tickets: SupportTicketsRepository,
        settings: PlatformSettingsRepository,
        notifications: SupportNotificationService,
        audit: AuditLog,
    ) -> None:
        self._agents = agents
        self._auth = auth
        self._tickets = tickets
        self._settings = settings
        self._notifications = notifications
        self._audit = audit

    async def handle_new_ticket(
        self, ticket: SupportTicketDocument
    ) -> SupportTicketDocument | None:
        if ticket.interest != SupportContactInterest.DMC:
            return ticket
        settings = await self._settings.get_or_create()
        if settings.dmc_assignment_mode != DmcAssignmentMode.ROUND_ROBIN:
            return ticket
        candidate = next_in_queue(await self.candidates())
        if candidate is None:
            await self._audit.record(
                AuditAction.TICKET_UNASSIGNED,
                resource_type="support_ticket",
                resource_id=ticket.id,
                after={"reason": "no_eligible_agent"},
            )
            return ticket
        return await self.assign(
            ticket.id,
            agent_user_id=candidate.user_id,
            mode="automatic",
            actor_user_id=None,
        )

    async def assign(
        self,
        ticket_id: UUID,
        *,
        agent_user_id: UUID,
        mode: AssignmentMode,
        actor_user_id: UUID | None,
    ) -> SupportTicketDocument:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        if ticket.interest != SupportContactInterest.DMC:
            raise ValidationAppError("Only DMC contact requests can be assigned to an agent.")

        agent_user = await self._auth.get_by_id(agent_user_id)
        agent_doc = await self._agents.get_by_user_id(agent_user_id)
        if (
            agent_user is None
            or agent_doc is None
            or agent_user.role != Role.DMC_AGENT
            or not agent_user.is_active
        ):
            raise ValidationAppError("Invalid or inactive DMC agent.")
        if mode == "automatic" and not agent_doc.available:
            raise ValidationAppError("DMC agent is unavailable for automatic assignment.")
        if ticket.assigned_agent_id == agent_user_id:
            return ticket

        previous = ticket.assigned_agent_id
        updated = await self._tickets.update(
            ticket.id, {"assigned_agent_id": agent_user_id}
        )
        ticket = updated or ticket
        now = utcnow()
        agent_patch: dict[str, object] = {"last_assigned_at": now}
        if mode == "automatic":
            agent_patch["queue_position"] = await self._agents.next_queue_position()
        await self._agents.update(agent_user_id, agent_patch)
        await self._notifications.notify_dmc_agent_assigned(ticket, agent_user)
        action = (
            AuditAction.TICKET_REASSIGNED if previous is not None else AuditAction.TICKET_ASSIGNED
        )
        await self._audit.record(
            action,
            resource_type="support_ticket",
            resource_id=ticket.id,
            actor_user_id=actor_user_id,
            before={"assigned_agent_id": previous, "mode": mode},
            after={"assigned_agent_id": agent_user_id, "mode": mode},
        )
        return ticket

    async def candidates(self) -> list[QueueCandidate]:
        agents = await self._agents.list_ordered()
        if not agents:
            return []
        users = await self._auth.get_by_ids([agent.user_id for agent in agents])
        by_id = {user.id: user for user in users}
        candidates: list[QueueCandidate] = []
        for agent in agents:
            user = by_id.get(agent.user_id)
            if user is None:
                continue
            candidates.append(
                QueueCandidate(
                    user_id=agent.user_id,
                    queue_position=agent.queue_position,
                    available=agent.available,
                    is_active=user.is_active,
                    role=user.role,
                    created_at=agent.created_at,
                )
            )
        return candidates


__all__ = ["DmcAssignmentService"]
