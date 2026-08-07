"""Dependency wiring for support services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import get_settings
from src.infrastructure.email.client import email_sender
from src.infrastructure.realtime.presence import PresenceService
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.infrastructure.realtime.support_pubsub import SupportRealtimePublisher
from src.modules.auth.repository import AuthRepository
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.support.controller import AdminSupportController, PublicSupportController, UserSupportController
from src.modules.support.notification_service import SupportNotificationService
from src.modules.support.repository import SupportMessagesRepository, SupportTicketsRepository
from src.modules.support.service import SupportService

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis


def build_support_service(db: AsyncDatabase, redis_client: Redis) -> SupportService:
    auth_repo = AuthRepository(db)
    tickets_repo = SupportTicketsRepository(db)
    messages_repo = SupportMessagesRepository(db)
    user_notifications_repo = UserNotificationsRepository(db)
    presence = PresenceService(redis_client)
    support_realtime = SupportRealtimePublisher(redis_client)
    notification_realtime = NotificationRealtimePublisher(redis_client)
    notifications = SupportNotificationService(
        auth_repo=auth_repo,
        user_notifications_repo=user_notifications_repo,
        email_sender=email_sender,
        notification_realtime=notification_realtime,
        presence=presence,
        settings=get_settings(),
    )
    return SupportService(
        tickets_repo=tickets_repo,
        messages_repo=messages_repo,
        auth_repo=auth_repo,
        realtime=support_realtime,
        notifications=notifications,
        presence=presence,
    )


def build_public_support_controller(db: AsyncDatabase, redis_client: Redis) -> PublicSupportController:
    return PublicSupportController(build_support_service(db, redis_client))


def build_user_support_controller(db: AsyncDatabase, redis_client: Redis) -> UserSupportController:
    return UserSupportController(build_support_service(db, redis_client))


def build_admin_support_controller(db: AsyncDatabase, redis_client: Redis) -> AdminSupportController:
    return AdminSupportController(build_support_service(db, redis_client))


__all__ = [
    "build_admin_support_controller",
    "build_public_support_controller",
    "build_support_service",
    "build_user_support_controller",
]
