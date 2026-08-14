"""Persistence models for billing / subscriptions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument
from src.shared.utils.ids import new_uuid

BILLING_SETTINGS_ID = UUID("00000000-0000-4000-8000-000000000001")


class PlanCycle(StrEnum):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class BillingType(StrEnum):
    PIX = "PIX"
    BOLETO = "BOLETO"
    CREDIT_CARD = "CREDIT_CARD"


class CouponDiscountType(StrEnum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


class FineType(StrEnum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


class SubscriptionStatus(StrEnum):
    PENDING = "pending"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RECEIVED = "received"
    OVERDUE = "overdue"
    REFUNDED = "refunded"
    DELETED = "deleted"
    OTHER = "other"


ACCESS_STATUSES: frozenset[SubscriptionStatus] = frozenset(
    {
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }
)

OPEN_SUBSCRIPTION_STATUSES: frozenset[SubscriptionStatus] = frozenset(
    {
        SubscriptionStatus.PENDING,
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }
)


class BillingPlanDocument(DomainDocument):
    collection_name: ClassVar[str] = "billing_plans"

    name: str
    description: str | None = None
    features: list[str] = Field(default_factory=list)
    price: float = Field(..., ge=0, description="Amount in BRL.")
    cycle: PlanCycle = PlanCycle.MONTHLY
    is_active: bool = True
    sort_order: int = 0
    trial_days: int | None = Field(default=None, ge=0, description="Override global trial.")


class BillingSettingsDocument(DomainDocument):
    collection_name: ClassVar[str] = "billing_settings"

    id: UUID = Field(default=BILLING_SETTINGS_ID, alias="_id")
    trial_enabled: bool = True
    default_trial_days: int = Field(default=7, ge=0, le=365)
    allowed_billing_types: list[BillingType] = Field(
        default_factory=lambda: [BillingType.PIX, BillingType.BOLETO, BillingType.CREDIT_CARD]
    )
    fine_value: float = Field(default=2.0, ge=0)
    fine_type: FineType = FineType.PERCENTAGE
    interest_value: float = Field(default=1.0, ge=0, description="Monthly interest percent.")
    grace_period_days: int = Field(default=3, ge=0, le=90)


class BillingCouponDocument(DomainDocument):
    collection_name: ClassVar[str] = "billing_coupons"

    code: str
    discount_type: CouponDiscountType
    discount_value: float = Field(..., gt=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    used_count: int = 0
    applicable_plan_ids: list[UUID] = Field(default_factory=list)
    is_active: bool = True


class BillingSubscriptionDocument(DomainDocument):
    collection_name: ClassVar[str] = "billing_subscriptions"

    company_id: UUID
    user_id: UUID
    plan_id: UUID
    status: SubscriptionStatus = SubscriptionStatus.PENDING
    billing_type: BillingType
    coupon_code: str | None = None
    price: float
    cycle: PlanCycle
    asaas_customer_id: str | None = None
    asaas_subscription_id: str | None = None
    asaas_checkout_id: str | None = None
    checkout_url: str | None = None
    invoice_url: str | None = None
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    cancelled_at: datetime | None = None
    past_due_since: datetime | None = None


class BillingInvoiceDocument(DomainDocument):
    collection_name: ClassVar[str] = "billing_invoices"

    subscription_id: UUID
    company_id: UUID
    asaas_payment_id: str
    asaas_subscription_id: str | None = None
    value: float
    due_date: datetime | None = None
    status: InvoiceStatus = InvoiceStatus.PENDING
    asaas_status: str | None = None
    billing_type: str | None = None
    invoice_url: str | None = None
    bank_slip_url: str | None = None
    pix_qr_code: str | None = None
    pix_copy_paste: str | None = None
    paid_at: datetime | None = None


class BillingWebhookEventDocument(DomainDocument):
    collection_name: ClassVar[str] = "billing_webhook_events"

    asaas_event_id: str
    event: str
    processed: bool = True


def new_plan_id() -> UUID:
    return new_uuid()


__all__ = [
    "ACCESS_STATUSES",
    "BILLING_SETTINGS_ID",
    "BillingCouponDocument",
    "BillingInvoiceDocument",
    "BillingPlanDocument",
    "BillingSettingsDocument",
    "BillingSubscriptionDocument",
    "BillingType",
    "BillingWebhookEventDocument",
    "CouponDiscountType",
    "FineType",
    "InvoiceStatus",
    "OPEN_SUBSCRIPTION_STATUSES",
    "PlanCycle",
    "SubscriptionStatus",
    "new_plan_id",
]
