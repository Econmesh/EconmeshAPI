"""Dependency wiring for DMC services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import get_settings
from src.infrastructure.email.client import email_sender
from src.infrastructure.realtime.presence import PresenceService
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.infrastructure.realtime.support_pubsub import SupportRealtimePublisher
from src.modules.auth.repository import AuthRepository
from src.modules.billing.deps import build_billing_service
from src.modules.companies.repository import CompaniesRepository
from src.modules.dmc.admin_service import DmcAdminService
from src.modules.dmc.agent_service import DmcAgentService
from src.modules.dmc.assignment import DmcAssignmentService
from src.modules.dmc.audit import AuditLog
from src.modules.dmc.repository import (
    AuditEventsRepository,
    DmcAgentsRepository,
    DmcConversationMessagesRepository,
    DmcConversationsRepository,
    DmcNotificationBatchesRepository,
    DmcPortfolioRepository,
)
from src.modules.dmc.scope import ScopeService
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.opportunities.service import OpportunitiesService
from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.modules.support.notification_service import SupportNotificationService
from src.modules.support.repository import SupportMessagesRepository, SupportTicketsRepository
from src.modules.users.repository import UsersRepository

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

    from src.modules.dmc.portal import DmcPortalService


def build_support_notifications(
    db: AsyncDatabase, redis_client: Redis
) -> SupportNotificationService:
    return SupportNotificationService(
        auth_repo=AuthRepository(db),
        user_notifications_repo=UserNotificationsRepository(db),
        email_sender=email_sender,
        notification_realtime=NotificationRealtimePublisher(redis_client),
        presence=PresenceService(redis_client),
        settings=get_settings(),
    )


def build_assignment_service(db: AsyncDatabase, redis_client: Redis) -> DmcAssignmentService:
    return DmcAssignmentService(
        agents=DmcAgentsRepository(db),
        auth=AuthRepository(db),
        tickets=SupportTicketsRepository(db),
        settings=PlatformSettingsRepository(db),
        notifications=build_support_notifications(db, redis_client),
        audit=AuditLog(AuditEventsRepository(db)),
    )


def build_scope_service(db: AsyncDatabase) -> ScopeService:
    return ScopeService(
        DmcPortfolioRepository(db),
        CompaniesRepository(db),
        UsersRepository(db),
    )


def build_agent_service(db: AsyncDatabase, redis_client: Redis) -> DmcAgentService:
    auth = AuthRepository(db)
    companies = CompaniesRepository(db)
    opportunities = OpportunitiesService(
        OpportunitiesRepository(db),
        auth,
        companies,
        build_billing_service(db),
    )
    return DmcAgentService(
        auth=auth,
        companies=companies,
        scope=build_scope_service(db),
        conversations=DmcConversationsRepository(db),
        messages=DmcConversationMessagesRepository(db),
        batches=DmcNotificationBatchesRepository(db),
        user_notifications=UserNotificationsRepository(db),
        tickets=SupportTicketsRepository(db),
        ticket_messages=SupportMessagesRepository(db),
        opportunities=opportunities,
        support_notifications=build_support_notifications(db, redis_client),
        audit=AuditLog(AuditEventsRepository(db)),
        portfolio=DmcPortfolioRepository(db),
        notification_realtime=NotificationRealtimePublisher(redis_client),
        support_realtime=SupportRealtimePublisher(redis_client),
    )


def build_admin_service(db: AsyncDatabase, redis_client: Redis) -> DmcAdminService:
    return DmcAdminService(
        agents=DmcAgentsRepository(db),
        portfolio=DmcPortfolioRepository(db),
        auth=AuthRepository(db),
        companies=CompaniesRepository(db),
        tickets=SupportTicketsRepository(db),
        settings=PlatformSettingsRepository(db),
        assignment=build_assignment_service(db, redis_client),
        scope=build_scope_service(db),
        audit=AuditLog(AuditEventsRepository(db)),
        audit_events=AuditEventsRepository(db),
    )


def build_portal_service(db: AsyncDatabase, redis_client: Redis) -> DmcPortalService:
    from src.modules.dmc.portal import DmcPortalService
    from src.modules.support.deps import build_support_service

    return DmcPortalService(
        auth=AuthRepository(db),
        users=UsersRepository(db),
        companies=CompaniesRepository(db),
        support=build_support_service(db, redis_client),
    )


__all__ = [
    "build_admin_service",
    "build_agent_service",
    "build_assignment_service",
    "build_portal_service",
    "build_scope_service",
    "build_support_notifications",
]
