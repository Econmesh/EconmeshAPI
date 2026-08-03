"""Dependency wiring for conversations services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import get_settings
from src.infrastructure.email.client import email_sender
from src.infrastructure.realtime.conversation_pubsub import ConversationRealtimePublisher
from src.infrastructure.realtime.presence import PresenceService
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.modules.auth.repository import AuthRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.conversations.controller import (
    AdminConversationsController,
    UserConversationsController,
)
from src.modules.conversations.notification_service import ConversationNotificationService
from src.modules.conversations.repository import (
    ConversationMessagesRepository,
    ConversationsRepository,
)
from src.modules.conversations.service import ConversationsService
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.opportunities.repository import OpportunitiesRepository

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis


def build_conversations_service(
    db: AsyncDatabase, redis_client: Redis
) -> ConversationsService:
    auth_repo = AuthRepository(db)
    conversations_repo = ConversationsRepository(db)
    messages_repo = ConversationMessagesRepository(db)
    opportunities_repo = OpportunitiesRepository(db)
    companies_repo = CompaniesRepository(db)
    user_notifications_repo = UserNotificationsRepository(db)
    presence = PresenceService(redis_client)
    conversation_realtime = ConversationRealtimePublisher(redis_client)
    notification_realtime = NotificationRealtimePublisher(redis_client)
    notifications = ConversationNotificationService(
        auth_repo=auth_repo,
        user_notifications_repo=user_notifications_repo,
        email_sender=email_sender,
        notification_realtime=notification_realtime,
        presence=presence,
        settings=get_settings(),
    )
    return ConversationsService(
        conversations_repo=conversations_repo,
        messages_repo=messages_repo,
        opportunities_repo=opportunities_repo,
        companies_repo=companies_repo,
        auth_repo=auth_repo,
        realtime=conversation_realtime,
        notifications=notifications,
        presence=presence,
    )


def build_user_conversations_controller(
    db: AsyncDatabase, redis_client: Redis
) -> UserConversationsController:
    return UserConversationsController(build_conversations_service(db, redis_client))


def build_admin_conversations_controller(
    db: AsyncDatabase, redis_client: Redis
) -> AdminConversationsController:
    return AdminConversationsController(build_conversations_service(db, redis_client))


__all__ = [
    "build_admin_conversations_controller",
    "build_conversations_service",
    "build_user_conversations_controller",
]
