"""Dependency wiring for billing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from src.infrastructure.providers.payment.asaas import AsaasPaymentProvider
from src.modules.auth.repository import AuthRepository
from src.modules.billing.controller import (
    AdminBillingController,
    BillingController,
    BillingWebhookController,
)
from src.modules.billing.repository import BillingRepository
from src.modules.billing.service import BillingService
from src.modules.companies.repository import CompaniesRepository
from src.modules.users.repository import UsersRepository
from src.shared.dependencies.auth import CurrentUser, get_current_user
from src.shared.dependencies.db import get_db

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


def build_billing_service(db: AsyncDatabase) -> BillingService:
    return BillingService(
        repo=BillingRepository(db),
        auth_repo=AuthRepository(db),
        companies_repo=CompaniesRepository(db),
        users_repo=UsersRepository(db),
        asaas=AsaasPaymentProvider(),
    )


def build_billing_controller(db: AsyncDatabase) -> BillingController:
    return BillingController(build_billing_service(db))


def build_admin_billing_controller(db: AsyncDatabase) -> AdminBillingController:
    return AdminBillingController(build_billing_service(db))


def build_billing_webhook_controller(db: AsyncDatabase) -> BillingWebhookController:
    return BillingWebhookController(build_billing_service(db))


async def require_active_subscription(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> CurrentUser:
    """Block product routes until the company has a valid subscription."""
    service = build_billing_service(db)
    await service.assert_access(user.uid, is_admin=user.is_admin)
    return user


__all__ = [
    "build_admin_billing_controller",
    "build_billing_controller",
    "build_billing_service",
    "build_billing_webhook_controller",
    "require_active_subscription",
]
