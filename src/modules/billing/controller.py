"""HTTP controllers for billing."""

from __future__ import annotations

from uuid import UUID

from src.modules.billing.schema import (
    AccessGrantCreate,
    AccessGrantListParams,
    AdminSubscriptionListParams,
    BillingCouponCreate,
    BillingCouponUpdate,
    BillingPlanCreate,
    BillingPlanUpdate,
    BillingSettingsUpdate,
    CouponValidateRequest,
    SubscribeRequest,
)
from src.modules.billing.service import BillingService
from src.shared.schemas.pagination import PaginationParams


class BillingController:
    def __init__(self, service: BillingService) -> None:
        self._service = service

    async def me(self, *, firebase_uid: str, is_admin: bool):
        return await self._service.get_me(firebase_uid=firebase_uid, is_admin=is_admin)

    async def list_plans(self, pagination: PaginationParams):
        return await self._service.list_plans(pagination, active_only=True)

    async def validate_coupon(self, payload: CouponValidateRequest):
        return await self._service.validate_coupon(payload)

    async def subscribe(self, payload: SubscribeRequest, *, firebase_uid: str):
        return await self._service.subscribe(payload, firebase_uid=firebase_uid)

    async def get_subscription(self, *, firebase_uid: str):
        return await self._service.get_subscription(firebase_uid=firebase_uid)

    async def cancel_subscription(self, *, firebase_uid: str):
        return await self._service.cancel_subscription(firebase_uid=firebase_uid)

    async def list_invoices(self, pagination: PaginationParams, *, firebase_uid: str):
        return await self._service.list_invoices(pagination, firebase_uid=firebase_uid)


class AdminBillingController:
    def __init__(self, service: BillingService) -> None:
        self._service = service

    async def list_plans(self, pagination: PaginationParams):
        return await self._service.list_plans(pagination, active_only=False)

    async def create_plan(self, payload: BillingPlanCreate):
        return await self._service.create_plan(payload)

    async def get_plan(self, plan_id: UUID):
        return await self._service.get_plan(plan_id)

    async def update_plan(self, plan_id: UUID, payload: BillingPlanUpdate):
        return await self._service.update_plan(plan_id, payload)

    async def get_settings(self):
        return await self._service.get_settings()

    async def update_settings(self, payload: BillingSettingsUpdate):
        return await self._service.update_settings(payload)

    async def list_coupons(self, pagination: PaginationParams):
        return await self._service.list_coupons(pagination)

    async def create_coupon(self, payload: BillingCouponCreate):
        return await self._service.create_coupon(payload)

    async def get_coupon(self, coupon_id: UUID):
        return await self._service.get_coupon(coupon_id)

    async def update_coupon(self, coupon_id: UUID, payload: BillingCouponUpdate):
        return await self._service.update_coupon(coupon_id, payload)

    async def list_subscriptions(self, params: AdminSubscriptionListParams):
        return await self._service.admin_list_subscriptions(params)

    async def get_subscription(self, subscription_id: UUID):
        return await self._service.admin_get_subscription(subscription_id)

    async def list_subscription_invoices(
        self, subscription_id: UUID, pagination: PaginationParams
    ):
        return await self._service.admin_list_subscription_invoices(
            subscription_id, pagination
        )

    async def list_pending_users(self, pagination: PaginationParams):
        return await self._service.admin_list_pending_users(pagination)

    async def create_access_grant(self, payload: AccessGrantCreate, *, firebase_uid: str):
        return await self._service.admin_create_access_grant(
            payload, firebase_uid=firebase_uid
        )

    async def search_access_grant_targets(self, q: str):
        return await self._service.admin_search_access_grant_targets(q)

    async def list_access_grants(self, params: AccessGrantListParams):
        return await self._service.admin_list_access_grants(params)

    async def revoke_access_grant(self, grant_id: UUID):
        return await self._service.admin_revoke_access_grant(grant_id)


class BillingWebhookController:
    def __init__(self, service: BillingService) -> None:
        self._service = service

    async def handle(self, payload: dict, token: str | None):
        return await self._service.handle_webhook(payload, token)


__all__ = ["AdminBillingController", "BillingController", "BillingWebhookController"]
