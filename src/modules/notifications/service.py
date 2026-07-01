"""Business logic for notifications."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.exceptions import NotFoundError, ValidationAppError
from src.core.logging import get_logger
from src.infrastructure.email.client import EmailSender
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.modules.auth.model import UserDocument
from src.modules.notifications.model import (
    NotificationCampaignDocument,
    NotificationCampaignStats,
    NotificationCampaignStatus,
    NotificationChannel,
    NotificationGroupDocument,
    NotificationTargetType,
    UserNotificationDocument,
)
from src.modules.notifications.repository import (
    NotificationCampaignsRepository,
    NotificationGroupsRepository,
    UserNotificationsRepository,
)
from src.modules.notifications.schema import (
    NotificationCampaignCreate,
    NotificationCampaignListResponse,
    NotificationCampaignResponse,
    NotificationCampaignStatsResponse,
    NotificationGroupCreate,
    NotificationGroupListResponse,
    NotificationGroupResponse,
    NotificationGroupUpdate,
    UnreadCountResponse,
    UserNotificationListResponse,
    UserNotificationResponse,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from src.modules.auth.repository import AuthRepository

logger = get_logger(__name__)


def _group_to_response(doc: NotificationGroupDocument) -> NotificationGroupResponse:
    return NotificationGroupResponse(
        id=doc.id,
        name=doc.name,
        description=doc.description,
        user_ids=doc.user_ids,
        created_by=doc.created_by,
        is_active=doc.is_active,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _campaign_to_response(
    doc: NotificationCampaignDocument,
) -> NotificationCampaignResponse:
    return NotificationCampaignResponse(
        id=doc.id,
        title=doc.title,
        body=doc.body,
        channels=doc.channels,
        target_type=doc.target_type,
        target_user_ids=doc.target_user_ids,
        target_group_ids=doc.target_group_ids,
        send_at=doc.send_at,
        status=doc.status,
        stats=NotificationCampaignStatsResponse(
            total=doc.stats.total,
            delivered=doc.stats.delivered,
            failed=doc.stats.failed,
        ),
        created_by=doc.created_by,
        sent_at=doc.sent_at,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _user_notification_to_response(
    doc: UserNotificationDocument,
) -> UserNotificationResponse:
    return UserNotificationResponse(
        id=doc.id,
        title=doc.title,
        body=doc.body,
        read_at=doc.read_at,
        created_at=doc.created_at,
        campaign_id=doc.campaign_id,
        kind=doc.kind,
        metadata=doc.metadata,
    )


class NotificationGroupsService:
    def __init__(
        self,
        groups_repo: NotificationGroupsRepository,
        auth_repo: AuthRepository,
    ) -> None:
        self._groups_repo = groups_repo
        self._auth_repo = auth_repo

    async def _validate_user_ids(self, user_ids: list[UUID]) -> None:
        if not user_ids:
            return
        found = await self._auth_repo.get_by_ids(user_ids, active_only=True)
        found_ids = {user.id for user in found}
        missing = [str(uid) for uid in user_ids if uid not in found_ids]
        if missing:
            raise ValidationAppError(
                "One or more user IDs are invalid or inactive.",
                details={"missing_user_ids": missing},
            )

    async def create(
        self, payload: NotificationGroupCreate, *, created_by: UUID
    ) -> NotificationGroupResponse:
        await self._validate_user_ids(payload.user_ids)
        doc = NotificationGroupDocument(
            name=payload.name,
            description=payload.description,
            user_ids=payload.user_ids,
            created_by=created_by,
        )
        created = await self._groups_repo.create(doc)
        return _group_to_response(created)

    async def get(self, group_id: UUID) -> NotificationGroupResponse:
        doc = await self._groups_repo.get_by_id(group_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Notification group not found.")
        return _group_to_response(doc)

    async def list(
        self, *, page: int, page_size: int
    ) -> NotificationGroupListResponse:
        skip = (page - 1) * page_size
        items = await self._groups_repo.list_groups(skip=skip, limit=page_size)
        total = await self._groups_repo.count_groups()
        return NotificationGroupListResponse(
            items=[_group_to_response(doc) for doc in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update(
        self, group_id: UUID, payload: NotificationGroupUpdate
    ) -> NotificationGroupResponse:
        existing = await self._groups_repo.get_by_id(group_id)
        if existing is None:
            raise NotFoundError("Notification group not found.")

        patch = payload.model_dump(exclude_unset=True)
        if "user_ids" in patch and patch["user_ids"] is not None:
            await self._validate_user_ids(patch["user_ids"])

        updated = await self._groups_repo.update(group_id, patch)
        if updated is None:
            raise NotFoundError("Notification group not found.")
        return _group_to_response(updated)

    async def delete(self, group_id: UUID) -> None:
        existing = await self._groups_repo.get_by_id(group_id)
        if existing is None or not existing.is_active:
            raise NotFoundError("Notification group not found.")
        await self._groups_repo.soft_delete(group_id)


class NotificationsDeliveryService:
    def __init__(
        self,
        campaigns_repo: NotificationCampaignsRepository,
        groups_repo: NotificationGroupsRepository,
        user_notifications_repo: UserNotificationsRepository,
        auth_repo: AuthRepository,
        email_sender: EmailSender,
        realtime_publisher: NotificationRealtimePublisher | None = None,
    ) -> None:
        self._campaigns_repo = campaigns_repo
        self._groups_repo = groups_repo
        self._user_notifications_repo = user_notifications_repo
        self._auth_repo = auth_repo
        self._email_sender = email_sender
        self._realtime = realtime_publisher

    async def resolve_recipient_ids(
        self, campaign: NotificationCampaignDocument
    ) -> list[UUID]:
        if campaign.target_type is NotificationTargetType.ALL:
            return await self._auth_repo.list_active_user_ids()

        user_ids: set[UUID] = set()

        if campaign.target_type is NotificationTargetType.USERS:
            user_ids.update(campaign.target_user_ids)

        if campaign.target_type is NotificationTargetType.GROUPS:
            groups = await self._groups_repo.get_by_ids(campaign.target_group_ids)
            for group in groups:
                user_ids.update(group.user_ids)

        if not user_ids:
            return []

        active_users = await self._auth_repo.get_by_ids(
            list(user_ids), active_only=True
        )
        return [user.id for user in active_users]

    async def deliver(self, campaign_id: UUID) -> NotificationCampaignResponse:
        campaign = await self._campaigns_repo.get_by_id(campaign_id)
        if campaign is None:
            raise NotFoundError("Notification campaign not found.")

        if campaign.status in {
            NotificationCampaignStatus.SENT,
            NotificationCampaignStatus.CANCELLED,
        }:
            return _campaign_to_response(campaign)

        claimed = await self._campaigns_repo.claim_for_processing(campaign_id)
        if claimed is None:
            campaign = await self._campaigns_repo.get_by_id(campaign_id)
            if campaign is None:
                raise NotFoundError("Notification campaign not found.")
            return _campaign_to_response(campaign)

        try:
            recipient_ids = await self.resolve_recipient_ids(claimed)
            users = await self._auth_repo.get_by_ids(recipient_ids, active_only=True)
            delivered = 0
            failed = 0

            send_in_app = NotificationChannel.IN_APP in claimed.channels
            send_email = NotificationChannel.EMAIL in claimed.channels

            for user in users:
                try:
                    if send_in_app:
                        await self._deliver_in_app(claimed, user)
                    if send_email and user.email:
                        await self._email_sender.send_notification(
                            to=user.email,
                            subject=claimed.title,
                            body=claimed.body,
                        )
                    delivered += 1
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "notification_delivery_failed",
                        campaign_id=str(campaign_id),
                        user_id=str(user.id),
                    )
                    failed += 1

            now = utcnow()
            stats = NotificationCampaignStats(
                total=len(users),
                delivered=delivered,
                failed=failed,
            )
            status = (
                NotificationCampaignStatus.FAILED
                if delivered == 0 and len(users) > 0
                else NotificationCampaignStatus.SENT
            )
            updated = await self._campaigns_repo.update(
                campaign_id,
                {
                    "status": status.value,
                    "stats": stats.model_dump(),
                    "sent_at": now,
                },
            )
            return _campaign_to_response(updated or claimed)
        except Exception as exc:  # noqa: BLE001
            logger.exception("notification_campaign_failed", campaign_id=str(campaign_id))
            await self._campaigns_repo.update(
                campaign_id,
                {
                    "status": NotificationCampaignStatus.FAILED.value,
                    "error_message": str(exc),
                },
            )
            raise

    async def _deliver_in_app(
        self, campaign: NotificationCampaignDocument, user: UserDocument
    ) -> UserNotificationDocument:
        doc = UserNotificationDocument(
            user_id=user.id,
            campaign_id=campaign.id,
            title=campaign.title,
            body=campaign.body,
            channel=NotificationChannel.IN_APP,
        )
        created = await self._user_notifications_repo.create(doc)

        if self._realtime is not None:
            await self._realtime.publish_user_notification(
                user.id,
                {
                    "id": str(created.id),
                    "title": created.title,
                    "body": created.body,
                    "created_at": created.created_at.isoformat(),
                    "read_at": None,
                    "campaign_id": str(campaign.id) if campaign.id else None,
                    "kind": created.kind,
                    "metadata": created.metadata,
                },
            )
        return created


class NotificationCampaignsService:
    def __init__(
        self,
        campaigns_repo: NotificationCampaignsRepository,
        delivery_service: NotificationsDeliveryService,
        auth_repo: AuthRepository,
    ) -> None:
        self._campaigns_repo = campaigns_repo
        self._delivery_service = delivery_service
        self._auth_repo = auth_repo

    async def _resolve_admin_id(self, firebase_uid: str) -> UUID:
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        return user.id

    async def create(
        self, payload: NotificationCampaignCreate, *, firebase_uid: str
    ) -> NotificationCampaignResponse:
        created_by = await self._resolve_admin_id(firebase_uid)
        now = utcnow()
        immediate = payload.send_at is None or payload.send_at <= now

        doc = NotificationCampaignDocument(
            title=payload.title,
            body=payload.body,
            channels=payload.channels,
            target_type=payload.target_type,
            target_user_ids=payload.target_user_ids,
            target_group_ids=payload.target_group_ids,
            send_at=payload.send_at,
            status=(
                NotificationCampaignStatus.DRAFT
                if immediate
                else NotificationCampaignStatus.SCHEDULED
            ),
            created_by=created_by,
        )

        created = await self._campaigns_repo.create(doc)

        if immediate:
            return await self._delivery_service.deliver(created.id)
        return _campaign_to_response(created)

    async def get(self, campaign_id: UUID) -> NotificationCampaignResponse:
        doc = await self._campaigns_repo.get_by_id(campaign_id)
        if doc is None:
            raise NotFoundError("Notification campaign not found.")
        return _campaign_to_response(doc)

    async def list(
        self, *, page: int, page_size: int
    ) -> NotificationCampaignListResponse:
        skip = (page - 1) * page_size
        items = await self._campaigns_repo.list_campaigns(skip=skip, limit=page_size)
        total = await self._campaigns_repo.count_campaigns()
        return NotificationCampaignListResponse(
            items=[_campaign_to_response(doc) for doc in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def cancel(self, campaign_id: UUID) -> NotificationCampaignResponse:
        doc = await self._campaigns_repo.get_by_id(campaign_id)
        if doc is None:
            raise NotFoundError("Notification campaign not found.")
        if doc.status is not NotificationCampaignStatus.SCHEDULED:
            raise ValidationAppError(
                "Only scheduled campaigns can be cancelled.",
                details={"status": doc.status},
            )
        updated = await self._campaigns_repo.update(
            campaign_id, {"status": NotificationCampaignStatus.CANCELLED.value}
        )
        if updated is None:
            raise NotFoundError("Notification campaign not found.")
        return _campaign_to_response(updated)

    async def send_now(self, campaign_id: UUID) -> NotificationCampaignResponse:
        doc = await self._campaigns_repo.get_by_id(campaign_id)
        if doc is None:
            raise NotFoundError("Notification campaign not found.")
        if doc.status in {
            NotificationCampaignStatus.SENT,
            NotificationCampaignStatus.CANCELLED,
            NotificationCampaignStatus.PROCESSING,
        }:
            raise ValidationAppError(
                "Campaign cannot be sent in its current state.",
                details={"status": doc.status},
            )
        await self._campaigns_repo.update(
            campaign_id,
            {
                "status": NotificationCampaignStatus.DRAFT.value,
                "send_at": None,
            },
        )
        return await self._delivery_service.deliver(campaign_id)


class UserNotificationsService:
    def __init__(
        self,
        user_notifications_repo: UserNotificationsRepository,
        auth_repo: AuthRepository,
    ) -> None:
        self._repo = user_notifications_repo
        self._auth_repo = auth_repo

    async def _resolve_user_id(self, firebase_uid: str) -> UUID:
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        return user.id

    async def list(
        self,
        *,
        firebase_uid: str,
        page: int,
        page_size: int,
        unread_only: bool = False,
    ) -> UserNotificationListResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        skip = (page - 1) * page_size
        items = await self._repo.list_for_user(
            user_id, skip=skip, limit=page_size, unread_only=unread_only
        )
        total = await self._repo.count_for_user(user_id, unread_only=unread_only)
        return UserNotificationListResponse(
            items=[_user_notification_to_response(doc) for doc in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def unread_count(self, *, firebase_uid: str) -> UnreadCountResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        count = await self._repo.count_for_user(user_id, unread_only=True)
        return UnreadCountResponse(count=count)

    async def mark_read(
        self, notification_id: UUID, *, firebase_uid: str
    ) -> UserNotificationResponse:
        user_id = await self._resolve_user_id(firebase_uid)
        doc = await self._repo.mark_read(notification_id, user_id)
        if doc is None:
            raise NotFoundError("Notification not found.")
        return _user_notification_to_response(doc)

    async def mark_all_read(self, *, firebase_uid: str) -> int:
        user_id = await self._resolve_user_id(firebase_uid)
        return await self._repo.mark_all_read(user_id)


__all__ = [
    "NotificationCampaignsService",
    "NotificationGroupsService",
    "NotificationsDeliveryService",
    "UserNotificationsService",
]
