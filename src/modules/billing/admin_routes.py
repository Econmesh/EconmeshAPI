"""Admin billing routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.modules.billing.controller import AdminBillingController
from src.modules.billing.deps import build_admin_billing_controller
from src.modules.billing.schema import (
    AdminPendingUserListResponse,
    AdminSubscriptionListParams,
    AdminSubscriptionListItem,
    AdminSubscriptionListResponse,
    BillingCouponCreate,
    BillingCouponListResponse,
    BillingCouponResponse,
    BillingCouponUpdate,
    BillingInvoiceListResponse,
    BillingPlanCreate,
    BillingPlanListResponse,
    BillingPlanResponse,
    BillingPlanUpdate,
    BillingSettingsResponse,
    BillingSettingsUpdate,
)
from src.shared.constants.roles import Role
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_role
from src.shared.schemas.pagination import PaginationParams

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(
    prefix="/admin/billing",
    tags=["admin-billing"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> AdminBillingController:
    return build_admin_billing_controller(db)


ControllerDep = Annotated[AdminBillingController, Depends(_build_controller)]


@router.get("/plans", response_model=BillingPlanListResponse)
async def list_plans(
    controller: ControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> BillingPlanListResponse:
    return await controller.list_plans(pagination)


@router.post("/plans", response_model=BillingPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: BillingPlanCreate, controller: ControllerDep
) -> BillingPlanResponse:
    return await controller.create_plan(payload)


@router.get("/plans/{plan_id}", response_model=BillingPlanResponse)
async def get_plan(plan_id: UUID, controller: ControllerDep) -> BillingPlanResponse:
    return await controller.get_plan(plan_id)


@router.patch("/plans/{plan_id}", response_model=BillingPlanResponse)
async def update_plan(
    plan_id: UUID, payload: BillingPlanUpdate, controller: ControllerDep
) -> BillingPlanResponse:
    return await controller.update_plan(plan_id, payload)


@router.get("/settings", response_model=BillingSettingsResponse)
async def get_settings(controller: ControllerDep) -> BillingSettingsResponse:
    return await controller.get_settings()


@router.patch("/settings", response_model=BillingSettingsResponse)
async def update_settings(
    payload: BillingSettingsUpdate, controller: ControllerDep
) -> BillingSettingsResponse:
    return await controller.update_settings(payload)


@router.get("/coupons", response_model=BillingCouponListResponse)
async def list_coupons(
    controller: ControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> BillingCouponListResponse:
    return await controller.list_coupons(pagination)


@router.post(
    "/coupons", response_model=BillingCouponResponse, status_code=status.HTTP_201_CREATED
)
async def create_coupon(
    payload: BillingCouponCreate, controller: ControllerDep
) -> BillingCouponResponse:
    return await controller.create_coupon(payload)


@router.get("/coupons/{coupon_id}", response_model=BillingCouponResponse)
async def get_coupon(coupon_id: UUID, controller: ControllerDep) -> BillingCouponResponse:
    return await controller.get_coupon(coupon_id)


@router.patch("/coupons/{coupon_id}", response_model=BillingCouponResponse)
async def update_coupon(
    coupon_id: UUID, payload: BillingCouponUpdate, controller: ControllerDep
) -> BillingCouponResponse:
    return await controller.update_coupon(coupon_id, payload)


@router.get("/subscriptions", response_model=AdminSubscriptionListResponse)
async def list_subscriptions(
    controller: ControllerDep,
    params: Annotated[AdminSubscriptionListParams, Depends(AdminSubscriptionListParams.as_query)],
) -> AdminSubscriptionListResponse:
    return await controller.list_subscriptions(params)


@router.get("/subscriptions/pending-users", response_model=AdminPendingUserListResponse)
async def list_pending_users(
    controller: ControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> AdminPendingUserListResponse:
    return await controller.list_pending_users(pagination)


@router.get("/subscriptions/{subscription_id}", response_model=AdminSubscriptionListItem)
async def get_subscription(
    subscription_id: UUID, controller: ControllerDep
) -> AdminSubscriptionListItem:
    return await controller.get_subscription(subscription_id)


@router.get(
    "/subscriptions/{subscription_id}/invoices",
    response_model=BillingInvoiceListResponse,
)
async def list_subscription_invoices(
    subscription_id: UUID,
    controller: ControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> BillingInvoiceListResponse:
    return await controller.list_subscription_invoices(subscription_id, pagination)


__all__ = ["router"]
