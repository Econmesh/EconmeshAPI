"""DTOs for the ``billing`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Query
from pydantic import Field, field_validator

from src.modules.billing.model import (
    BillingType,
    CouponDiscountType,
    FineType,
    InvoiceStatus,
    PlanCycle,
    SubscriptionStatus,
)
from src.shared.schemas.base import APIModel


class BillingPlanCreate(APIModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    features: list[str] = Field(default_factory=list, max_length=30)
    price: float = Field(..., ge=0, le=1_000_000)
    cycle: PlanCycle = PlanCycle.MONTHLY
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)
    trial_days: int | None = Field(default=None, ge=0, le=365)

    @field_validator("features")
    @classmethod
    def _clean_features(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if text and text not in cleaned:
                cleaned.append(text[:200])
        return cleaned

    @field_validator("price")
    @classmethod
    def _round_price(cls, value: float) -> float:
        return round(value, 2)


class BillingPlanUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    features: list[str] | None = Field(default=None, max_length=30)
    price: float | None = Field(default=None, ge=0, le=1_000_000)
    cycle: PlanCycle | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    trial_days: int | None = Field(default=None, ge=0, le=365)

    @field_validator("features")
    @classmethod
    def _clean_features(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if text and text not in cleaned:
                cleaned.append(text[:200])
        return cleaned

    @field_validator("price")
    @classmethod
    def _round_price(cls, value: float | None) -> float | None:
        return None if value is None else round(value, 2)


class BillingPlanResponse(APIModel):
    id: UUID
    name: str
    description: str | None
    features: list[str]
    price: float
    cycle: PlanCycle
    is_active: bool
    sort_order: int
    trial_days: int | None
    created_at: datetime
    updated_at: datetime


class BillingPlanListResponse(APIModel):
    items: list[BillingPlanResponse]
    total: int
    page: int
    page_size: int


class BillingSettingsUpdate(APIModel):
    trial_enabled: bool | None = None
    default_trial_days: int | None = Field(default=None, ge=0, le=365)
    allowed_billing_types: list[BillingType] | None = None
    fine_value: float | None = Field(default=None, ge=0, le=100)
    fine_type: FineType | None = None
    interest_value: float | None = Field(default=None, ge=0, le=100)
    grace_period_days: int | None = Field(default=None, ge=0, le=90)


class BillingSettingsResponse(APIModel):
    id: UUID
    trial_enabled: bool
    default_trial_days: int
    allowed_billing_types: list[BillingType]
    fine_value: float
    fine_type: FineType
    interest_value: float
    grace_period_days: int
    updated_at: datetime


class BillingCouponCreate(APIModel):
    code: str = Field(..., min_length=3, max_length=40)
    discount_type: CouponDiscountType
    discount_value: float = Field(..., gt=0, le=100_000)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    applicable_plan_ids: list[UUID] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _upper_code(cls, value: str) -> str:
        cleaned = "".join(ch for ch in value.strip().upper() if ch.isalnum() or ch in "-_")
        if len(cleaned) < 3:
            raise ValueError("code must have at least 3 alphanumeric characters")
        return cleaned


class BillingCouponUpdate(APIModel):
    discount_type: CouponDiscountType | None = None
    discount_value: float | None = Field(default=None, gt=0, le=100_000)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    applicable_plan_ids: list[UUID] | None = None
    is_active: bool | None = None
    clear_valid_from: bool = False
    clear_valid_until: bool = False
    clear_max_uses: bool = False


class BillingCouponResponse(APIModel):
    id: UUID
    code: str
    discount_type: CouponDiscountType
    discount_value: float
    valid_from: datetime | None
    valid_until: datetime | None
    max_uses: int | None
    used_count: int
    applicable_plan_ids: list[UUID]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BillingCouponListResponse(APIModel):
    items: list[BillingCouponResponse]
    total: int
    page: int
    page_size: int


class CouponValidateRequest(APIModel):
    code: str = Field(..., min_length=3, max_length=40)
    plan_id: UUID

    @field_validator("code")
    @classmethod
    def _upper_code(cls, value: str) -> str:
        return value.strip().upper()


class CouponValidateResponse(APIModel):
    code: str
    discount_type: CouponDiscountType
    discount_value: float
    original_price: float
    discounted_price: float


class SubscribeRequest(APIModel):
    plan_id: UUID
    billing_type: BillingType
    coupon_code: str | None = Field(default=None, max_length=40)

    @field_validator("coupon_code")
    @classmethod
    def _upper_coupon(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None


class BillingSubscriptionResponse(APIModel):
    id: UUID
    company_id: UUID
    user_id: UUID
    plan_id: UUID
    plan_name: str | None = None
    status: SubscriptionStatus
    billing_type: BillingType
    coupon_code: str | None
    price: float
    cycle: PlanCycle
    checkout_url: str | None = None
    invoice_url: str | None = None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubscribeResponse(APIModel):
    subscription: BillingSubscriptionResponse
    checkout_url: str | None = None
    invoice_url: str | None = None


class BillingMeResponse(APIModel):
    status: SubscriptionStatus
    has_access: bool
    is_admin: bool = False
    company_id: UUID | None = None
    subscription: BillingSubscriptionResponse | None = None
    trial_enabled: bool = False
    trial_days: int = 0
    allowed_billing_types: list[BillingType] = Field(default_factory=list)


class BillingInvoiceResponse(APIModel):
    id: UUID
    subscription_id: UUID
    value: float
    due_date: datetime | None
    status: InvoiceStatus
    asaas_status: str | None
    billing_type: str | None
    invoice_url: str | None
    bank_slip_url: str | None
    pix_qr_code: str | None
    pix_copy_paste: str | None
    paid_at: datetime | None
    created_at: datetime


class BillingInvoiceListResponse(APIModel):
    items: list[BillingInvoiceResponse]
    total: int
    page: int
    page_size: int


class AdminSubscriptionListItem(APIModel):
    id: UUID
    company_id: UUID
    company_name: str | None = None
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    plan_id: UUID
    plan_name: str | None = None
    status: SubscriptionStatus
    billing_type: BillingType
    price: float
    cycle: PlanCycle
    coupon_code: str | None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class AdminSubscriptionListResponse(APIModel):
    items: list[AdminSubscriptionListItem]
    total: int
    page: int
    page_size: int


class AdminPendingUserItem(APIModel):
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    company_id: UUID | None = None
    company_name: str | None = None
    created_at: datetime | None = None


class AdminPendingUserListResponse(APIModel):
    items: list[AdminPendingUserItem]
    total: int
    page: int
    page_size: int


class AdminSubscriptionListParams(APIModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: SubscriptionStatus | None = None
    q: str | None = None

    @classmethod
    def as_query(
        cls,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        status: SubscriptionStatus | None = Query(None),
        q: str | None = Query(None, max_length=200),
    ) -> AdminSubscriptionListParams:
        return cls(page=page, page_size=page_size, status=status, q=q)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


__all__ = [
    "AdminPendingUserItem",
    "AdminPendingUserListResponse",
    "AdminSubscriptionListItem",
    "AdminSubscriptionListParams",
    "AdminSubscriptionListResponse",
    "BillingCouponCreate",
    "BillingCouponListResponse",
    "BillingCouponResponse",
    "BillingCouponUpdate",
    "BillingInvoiceListResponse",
    "BillingInvoiceResponse",
    "BillingMeResponse",
    "BillingPlanCreate",
    "BillingPlanListResponse",
    "BillingPlanResponse",
    "BillingPlanUpdate",
    "BillingSettingsResponse",
    "BillingSettingsUpdate",
    "BillingSubscriptionResponse",
    "CouponValidateRequest",
    "CouponValidateResponse",
    "SubscribeRequest",
    "SubscribeResponse",
]
