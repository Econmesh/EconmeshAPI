"""HTTP controller for ``notifications``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from src.modules.notifications.schema import (
    NotificationCampaignCreate,
    NotificationCampaignListResponse,
    NotificationCampaignResponse,
    NotificationGroupCreate,
    NotificationGroupListResponse,
    NotificationGroupResponse,
    NotificationGroupUpdate,
    UnreadCountResponse,
    UserNotificationListResponse,
    UserNotificationResponse,
)
from src.modules.notifications.service import (
    NotificationCampaignsService,
    NotificationGroupsService,
    UserNotificationsService,
)
from src.shared.dependencies.auth import CurrentUser


class AdminNotificationGroupsController:
    def __init__(self, service: NotificationGroupsService) -> None:
        self._service = service

    async def create(
        self,
        payload: NotificationGroupCreate,
        *,
        created_by: UUID,
    ) -> NotificationGroupResponse:
        return await self._service.create(payload, created_by=created_by)

    async def list(
        self, *, page: int, page_size: int
    ) -> NotificationGroupListResponse:
        return await self._service.list(page=page, page_size=page_size)

    async def get(self, group_id: UUID) -> NotificationGroupResponse:
        return await self._service.get(group_id)

    async def update(
        self, group_id: UUID, payload: NotificationGroupUpdate
    ) -> NotificationGroupResponse:
        return await self._service.update(group_id, payload)

    async def delete(self, group_id: UUID) -> None:
        await self._service.delete(group_id)


class AdminNotificationCampaignsController:
    def __init__(self, service: NotificationCampaignsService) -> None:
        self._service = service

    async def create(
        self, payload: NotificationCampaignCreate, current_user: CurrentUser
    ) -> NotificationCampaignResponse:
        return await self._service.create(payload, firebase_uid=current_user.uid)

    async def list(
        self, *, page: int, page_size: int
    ) -> NotificationCampaignListResponse:
        return await self._service.list(page=page, page_size=page_size)

    async def get(self, campaign_id: UUID) -> NotificationCampaignResponse:
        return await self._service.get(campaign_id)

    async def cancel(self, campaign_id: UUID) -> NotificationCampaignResponse:
        return await self._service.cancel(campaign_id)

    async def send_now(self, campaign_id: UUID) -> NotificationCampaignResponse:
        return await self._service.send_now(campaign_id)


class UserNotificationsController:
    def __init__(self, service: UserNotificationsService) -> None:
        self._service = service

    async def list(
        self,
        current_user: CurrentUser,
        *,
        page: int,
        page_size: int,
        unread_only: bool,
    ) -> UserNotificationListResponse:
        return await self._service.list(
            firebase_uid=current_user.uid,
            page=page,
            page_size=page_size,
            unread_only=unread_only,
        )

    async def unread_count(self, current_user: CurrentUser) -> UnreadCountResponse:
        return await self._service.unread_count(firebase_uid=current_user.uid)

    async def mark_read(
        self, notification_id: UUID, current_user: CurrentUser
    ) -> UserNotificationResponse:
        return await self._service.mark_read(
            notification_id, firebase_uid=current_user.uid
        )

    async def mark_all_read(self, current_user: CurrentUser) -> int:
        return await self._service.mark_all_read(firebase_uid=current_user.uid)


__all__ = [
    "AdminNotificationCampaignsController",
    "AdminNotificationGroupsController",
    "UserNotificationsController",
]
