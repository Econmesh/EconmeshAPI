"""Persistence models for notifications."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.schemas.base import DomainDocument


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"


class NotificationTargetType(StrEnum):
    ALL = "all"
    USERS = "users"
    GROUPS = "groups"


class NotificationCampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationGroupDocument(DomainDocument):
    """Reusable recipient group managed by admins."""

    collection_name: ClassVar[str] = "notification_groups"

    name: str
    description: str | None = None
    user_ids: list[UUID] = Field(default_factory=list)
    created_by: UUID
    is_active: bool = True


class NotificationCampaignStats(BaseModel):
    total: int = 0
    delivered: int = 0
    failed: int = 0


class NotificationCampaignDocument(DomainDocument):
    """Admin broadcast campaign."""

    collection_name: ClassVar[str] = "notification_campaigns"

    title: str
    body: str
    channels: list[NotificationChannel] = Field(default_factory=list)
    target_type: NotificationTargetType
    target_user_ids: list[UUID] = Field(default_factory=list)
    target_group_ids: list[UUID] = Field(default_factory=list)
    send_at: datetime | None = None
    status: NotificationCampaignStatus = NotificationCampaignStatus.DRAFT
    stats: NotificationCampaignStats = Field(default_factory=NotificationCampaignStats)
    created_by: UUID
    sent_at: datetime | None = None
    error_message: str | None = None


class NotificationKind(StrEnum):
    GENERAL = "general"
    SUPPORT = "support"
    AGREEMENT = "agreement"


class UserNotificationDocument(DomainDocument):
    """Per-user inbox notification."""

    collection_name: ClassVar[str] = "user_notifications"

    user_id: UUID
    campaign_id: UUID | None = None
    title: str
    body: str
    read_at: datetime | None = None
    channel: NotificationChannel = NotificationChannel.IN_APP
    kind: NotificationKind = NotificationKind.GENERAL
    metadata: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "NotificationKind",
    "NotificationCampaignDocument",
    "NotificationCampaignStats",
    "NotificationCampaignStatus",
    "NotificationChannel",
    "NotificationGroupDocument",
    "NotificationTargetType",
    "UserNotificationDocument",
]
