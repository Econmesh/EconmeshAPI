"""DTOs for the ``notifications`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from src.modules.notifications.model import (
    NotificationCampaignStatus,
    NotificationChannel,
    NotificationKind,
    NotificationTargetType,
)
from src.shared.schemas.base import APIModel
from src.shared.schemas.pagination import Page


# ------------------------------------------------------------------ groups
class NotificationGroupCreate(APIModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    user_ids: list[UUID] = Field(default_factory=list)


class NotificationGroupUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    user_ids: list[UUID] | None = None
    is_active: bool | None = None


class NotificationGroupResponse(APIModel):
    id: UUID
    name: str
    description: str | None
    user_ids: list[UUID]
    created_by: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationGroupListResponse(APIModel):
    items: list[NotificationGroupResponse]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------- campaigns
class NotificationCampaignCreate(APIModel):
    title: str = Field(..., min_length=2, max_length=200)
    body: str = Field(..., min_length=2, max_length=5000)
    channels: list[NotificationChannel] = Field(..., min_length=1)
    target_type: NotificationTargetType
    target_user_ids: list[UUID] = Field(default_factory=list)
    target_group_ids: list[UUID] = Field(default_factory=list)
    send_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_targets(self) -> NotificationCampaignCreate:
        if self.target_type is NotificationTargetType.USERS and not self.target_user_ids:
            raise ValueError("target_user_ids is required when target_type is users.")
        if self.target_type is NotificationTargetType.GROUPS and not self.target_group_ids:
            raise ValueError("target_group_ids is required when target_type is groups.")
        if NotificationChannel.IN_APP not in self.channels and NotificationChannel.EMAIL not in self.channels:
            raise ValueError("At least one valid channel is required.")
        return self


class NotificationCampaignStatsResponse(APIModel):
    total: int = 0
    delivered: int = 0
    failed: int = 0


class NotificationCampaignResponse(APIModel):
    id: UUID
    title: str
    body: str
    channels: list[NotificationChannel]
    target_type: NotificationTargetType
    target_user_ids: list[UUID]
    target_group_ids: list[UUID]
    send_at: datetime | None
    status: NotificationCampaignStatus
    stats: NotificationCampaignStatsResponse
    created_by: UUID
    sent_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class NotificationCampaignListResponse(APIModel):
    items: list[NotificationCampaignResponse]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------- user inbox
class UserNotificationResponse(APIModel):
    id: UUID
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime
    campaign_id: UUID | None = None
    kind: NotificationKind = NotificationKind.GENERAL
    metadata: dict[str, str] = Field(default_factory=dict)


class UserNotificationListResponse(APIModel):
    items: list[UserNotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(APIModel):
    count: int = Field(..., ge=0)


__all__ = [
    "NotificationCampaignCreate",
    "NotificationCampaignListResponse",
    "NotificationCampaignResponse",
    "NotificationGroupCreate",
    "NotificationGroupListResponse",
    "NotificationGroupResponse",
    "NotificationGroupUpdate",
    "UnreadCountResponse",
    "UserNotificationListResponse",
    "UserNotificationResponse",
]
