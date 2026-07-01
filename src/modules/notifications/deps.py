"""Dependency wiring for notification services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.email.client import email_sender
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.modules.auth.repository import AuthRepository
from src.modules.notifications.controller import (
    AdminNotificationCampaignsController,
    AdminNotificationGroupsController,
)
from src.modules.notifications.repository import (
    NotificationCampaignsRepository,
    NotificationGroupsRepository,
    UserNotificationsRepository,
)
from src.modules.notifications.service import (
    NotificationCampaignsService,
    NotificationGroupsService,
    NotificationsDeliveryService,
)

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis


def build_admin_notification_groups_controller(
    db: AsyncDatabase,
) -> AdminNotificationGroupsController:
    groups_repo = NotificationGroupsRepository(db)
    auth_repo = AuthRepository(db)
    service = NotificationGroupsService(groups_repo, auth_repo)
    return AdminNotificationGroupsController(service)


def build_admin_notification_campaigns_controller(
    db: AsyncDatabase,
    redis_client: Redis,
) -> AdminNotificationCampaignsController:
    campaigns_repo = NotificationCampaignsRepository(db)
    groups_repo = NotificationGroupsRepository(db)
    user_notifications_repo = UserNotificationsRepository(db)
    auth_repo = AuthRepository(db)
    realtime = NotificationRealtimePublisher(redis_client)
    delivery = NotificationsDeliveryService(
        campaigns_repo=campaigns_repo,
        groups_repo=groups_repo,
        user_notifications_repo=user_notifications_repo,
        auth_repo=auth_repo,
        email_sender=email_sender,
        realtime_publisher=realtime,
    )
    service = NotificationCampaignsService(
        campaigns_repo, delivery, auth_repo
    )
    return AdminNotificationCampaignsController(service)


__all__ = [
    "build_admin_notification_campaigns_controller",
    "build_admin_notification_groups_controller",
]
