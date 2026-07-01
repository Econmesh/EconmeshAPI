"""Background worker for scheduled notification campaigns."""

from __future__ import annotations

import asyncio

from src.core.database import mongo
from src.core.logging import get_logger, setup_logging
from src.infrastructure.email.client import email_sender
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.infrastructure.redis.client import redis_manager
from src.modules.auth.repository import AuthRepository
from src.modules.notifications.repository import (
    NotificationCampaignsRepository,
    NotificationGroupsRepository,
    UserNotificationsRepository,
)
from src.modules.notifications.service import NotificationsDeliveryService
from src.shared.utils.time import utcnow

logger = get_logger(__name__)

_POLL_INTERVAL_SECONDS = 60


def _build_delivery_service(db) -> NotificationsDeliveryService:
    campaigns_repo = NotificationCampaignsRepository(db)
    groups_repo = NotificationGroupsRepository(db)
    user_notifications_repo = UserNotificationsRepository(db)
    auth_repo = AuthRepository(db)
    realtime = NotificationRealtimePublisher(redis_manager.client)
    return NotificationsDeliveryService(
        campaigns_repo=campaigns_repo,
        groups_repo=groups_repo,
        user_notifications_repo=user_notifications_repo,
        auth_repo=auth_repo,
        email_sender=email_sender,
        realtime_publisher=realtime,
    )


async def _process_due_campaigns() -> None:
    db = mongo.db
    campaigns_repo = NotificationCampaignsRepository(db)
    delivery = _build_delivery_service(db)
    now = utcnow()
    due = await campaigns_repo.list_due_scheduled(now=now)
    for campaign in due:
        logger.info(
            "processing_scheduled_campaign",
            campaign_id=str(campaign.id),
            send_at=campaign.send_at.isoformat() if campaign.send_at else None,
        )
        try:
            await delivery.deliver(campaign.id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "scheduled_campaign_failed", campaign_id=str(campaign.id)
            )


async def main() -> None:
    setup_logging()
    await mongo.connect()
    await redis_manager.connect()
    logger.info("notifications_worker_started", interval=_POLL_INTERVAL_SECONDS)
    try:
        while True:
            await _process_due_campaigns()
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    finally:
        await redis_manager.close()
        await mongo.close()
        logger.info("notifications_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
