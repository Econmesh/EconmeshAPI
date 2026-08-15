"""Client billing routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status

from src.modules.billing.controller import BillingController
from src.modules.billing.deps import build_billing_controller
from src.modules.billing.schema import (
    BillingInvoiceListResponse,
    BillingMeResponse,
    BillingPlanListResponse,
    BillingSubscriptionResponse,
    CouponValidateRequest,
    CouponValidateResponse,
    SubscribeRequest,
    SubscribeResponse,
)
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.schemas.pagination import PaginationParams

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/billing", tags=["billing"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> BillingController:
    return build_billing_controller(db)


ControllerDep = Annotated[BillingController, Depends(_build_controller)]


@router.get("/me", response_model=BillingMeResponse, summary="Current billing status.")
async def get_billing_me(
    controller: ControllerDep, current_user: CurrentUserDep
) -> BillingMeResponse:
    return await controller.me(
        firebase_uid=current_user.uid, is_admin=current_user.is_admin
    )


@router.get("/plans", response_model=BillingPlanListResponse, summary="List active plans.")
async def list_plans(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> BillingPlanListResponse:
    _ = current_user
    return await controller.list_plans(pagination)


@router.post(
    "/coupons/validate",
    response_model=CouponValidateResponse,
    summary="Preview a coupon discount.",
)
async def validate_coupon(
    payload: CouponValidateRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> CouponValidateResponse:
    _ = current_user
    return await controller.validate_coupon(payload)


@router.post(
    "/subscribe",
    response_model=SubscribeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a subscription checkout.",
)
async def subscribe(
    payload: SubscribeRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> SubscribeResponse:
    return await controller.subscribe(payload, firebase_uid=current_user.uid)


@router.get(
    "/subscription",
    response_model=BillingSubscriptionResponse,
    summary="Get the current company subscription.",
)
async def get_subscription(
    controller: ControllerDep, current_user: CurrentUserDep
) -> BillingSubscriptionResponse:
    return await controller.get_subscription(firebase_uid=current_user.uid)


@router.post(
    "/subscription/cancel",
    response_model=BillingSubscriptionResponse,
    summary="Cancel the current subscription.",
)
async def cancel_subscription(
    controller: ControllerDep, current_user: CurrentUserDep
) -> BillingSubscriptionResponse:
    return await controller.cancel_subscription(firebase_uid=current_user.uid)


@router.get(
    "/invoices",
    response_model=BillingInvoiceListResponse,
    summary="List invoices for the current company.",
)
async def list_invoices(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> BillingInvoiceListResponse:
    return await controller.list_invoices(pagination, firebase_uid=current_user.uid)


__all__ = ["router"]
