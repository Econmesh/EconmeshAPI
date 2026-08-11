"""Dependency wiring for contract proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.email import email_sender
from src.infrastructure.realtime.conversation_pubsub import ConversationRealtimePublisher
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.modules.agreements.notification_service import AgreementNotificationService
from src.modules.agreements.repository import AgreementEventsRepository, AgreementsRepository
from src.modules.agreements.service import AgreementsService
from src.modules.auth.repository import AuthRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.contract_proposals.controller import ContractProposalsController
from src.modules.contract_proposals.repository import ContractProposalsRepository
from src.modules.contract_proposals.service import ContractProposalsService
from src.modules.contract_sections.repository import ContractSectionsRepository
from src.modules.conversations.repository import (
    ConversationMessagesRepository,
    ConversationsRepository,
)
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.users.repository import UsersRepository

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis


def build_contract_proposals_controller(
    db: AsyncDatabase,
    redis: Redis,
) -> ContractProposalsController:
    agreements = AgreementsService(
        AgreementsRepository(db),
        AgreementEventsRepository(db),
        AuthRepository(db),
        CompaniesRepository(db),
        UsersRepository(db),
        notifications=AgreementNotificationService(
            auth_repo=AuthRepository(db),
            user_notifications_repo=UserNotificationsRepository(db),
            email_sender=email_sender,
            notification_realtime=NotificationRealtimePublisher(redis),
        ),
        messages_repository=ConversationMessagesRepository(db),
        opportunities_repository=OpportunitiesRepository(db),
    )
    service = ContractProposalsService(
        repository=ContractProposalsRepository(db),
        conversations_repo=ConversationsRepository(db),
        companies_repo=CompaniesRepository(db),
        opportunities_repo=OpportunitiesRepository(db),
        sections_repo=ContractSectionsRepository(db),
        auth_repo=AuthRepository(db),
        agreements_service=agreements,
        messages_repo=ConversationMessagesRepository(db),
        realtime=ConversationRealtimePublisher(redis),
    )
    return ContractProposalsController(service)


def build_admin_contract_proposals_controller(
    db: AsyncDatabase,
    redis: Redis,
) -> ContractProposalsController:
    return build_contract_proposals_controller(db, redis)


__all__ = [
    "build_admin_contract_proposals_controller",
    "build_contract_proposals_controller",
]
