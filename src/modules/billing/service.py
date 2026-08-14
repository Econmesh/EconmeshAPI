"""Business rules for billing and Asaas subscriptions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pymongo.errors import DuplicateKeyError

from src.core.config import get_settings
from src.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from src.core.logging import get_logger
from src.infrastructure.providers.payment.asaas import AsaasPaymentProvider
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.billing.model import (
    ACCESS_STATUSES,
    BillingCouponDocument,
    BillingInvoiceDocument,
    BillingPlanDocument,
    BillingSettingsDocument,
    BillingSubscriptionDocument,
    BillingType,
    CouponDiscountType,
    InvoiceStatus,
    OPEN_SUBSCRIPTION_STATUSES,
    SubscriptionStatus,
)
from src.modules.billing.repository import BillingRepository
from src.modules.billing.schema import (
    AdminPendingUserItem,
    AdminPendingUserListResponse,
    AdminSubscriptionListItem,
    AdminSubscriptionListParams,
    AdminSubscriptionListResponse,
    BillingCouponCreate,
    BillingCouponListResponse,
    BillingCouponResponse,
    BillingCouponUpdate,
    BillingInvoiceListResponse,
    BillingInvoiceResponse,
    BillingMeResponse,
    BillingPlanCreate,
    BillingPlanListResponse,
    BillingPlanResponse,
    BillingPlanUpdate,
    BillingSettingsResponse,
    BillingSettingsUpdate,
    BillingSubscriptionResponse,
    CouponValidateRequest,
    CouponValidateResponse,
    SubscribeRequest,
    SubscribeResponse,
)
from src.modules.companies.model import CompanyDocument
from src.modules.companies.repository import CompaniesRepository
from src.modules.users.repository import UsersRepository
from src.shared.schemas.pagination import PaginationParams
from src.shared.schemas.responses import MessageResponse
from src.shared.utils.time import utcnow

logger = get_logger(__name__)

_ASAAS_INVOICE_STATUS: dict[str, InvoiceStatus] = {
    "PENDING": InvoiceStatus.PENDING,
    "CONFIRMED": InvoiceStatus.CONFIRMED,
    "RECEIVED": InvoiceStatus.RECEIVED,
    "RECEIVED_IN_CASH": InvoiceStatus.RECEIVED,
    "OVERDUE": InvoiceStatus.OVERDUE,
    "REFUNDED": InvoiceStatus.REFUNDED,
    "DELETED": InvoiceStatus.DELETED,
}


def _money(value: float) -> float:
    return round(float(value), 2)


def _digits(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isdigit())


def _parse_asaas_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text[:19] if fmt != "%Y-%m-%d" else text[:10], fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


class BillingService:
    def __init__(
        self,
        repo: BillingRepository,
        auth_repo: AuthRepository,
        companies_repo: CompaniesRepository,
        users_repo: UsersRepository,
        asaas: AsaasPaymentProvider | None = None,
    ) -> None:
        self._repo = repo
        self._auth_repo = auth_repo
        self._companies_repo = companies_repo
        self._users_repo = users_repo
        self._asaas = asaas or AsaasPaymentProvider()

    # ------------------------------------------------------------------ users
    async def _resolve_user(self, firebase_uid: str) -> UserDocument:
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    async def _resolve_company(self, user: UserDocument) -> CompanyDocument | None:
        profile = await self._users_repo.get_by_user(user.id)
        if profile and profile.company_id:
            company = await self._companies_repo.get(profile.company_id)
            if company and company.is_active:
                return company
        companies = await self._companies_repo.list_for_owner(user.id, skip=0, limit=1)
        return companies[0] if companies else None

    async def _require_company(self, user: UserDocument) -> CompanyDocument:
        company = await self._resolve_company(user)
        if company is None:
            raise ValidationAppError(
                "Cadastre uma empresa antes de assinar um plano.",
                code="company_required",
            )
        return company

    # ---------------------------------------------------------------- settings
    async def get_settings(self) -> BillingSettingsResponse:
        settings = await self._repo.settings.get_or_create()
        return self._settings_response(settings)

    async def update_settings(self, payload: BillingSettingsUpdate) -> BillingSettingsResponse:
        patch = payload.model_dump(exclude_unset=True)
        if "allowed_billing_types" in patch and patch["allowed_billing_types"] is not None:
            patch["allowed_billing_types"] = [
                t.value if hasattr(t, "value") else t for t in patch["allowed_billing_types"]
            ]
        if "fine_type" in patch and patch["fine_type"] is not None:
            patch["fine_type"] = getattr(patch["fine_type"], "value", patch["fine_type"])
        settings = await self._repo.settings.update(patch)
        return self._settings_response(settings)

    # ------------------------------------------------------------------- plans
    async def list_plans(
        self, pagination: PaginationParams, *, active_only: bool
    ) -> BillingPlanListResponse:
        items = await self._repo.plans.list_all(
            skip=pagination.skip, limit=pagination.limit, active_only=active_only
        )
        total = await self._repo.plans.count(active_only=active_only)
        return BillingPlanListResponse(
            items=[self._plan_response(p) for p in items],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def create_plan(self, payload: BillingPlanCreate) -> BillingPlanResponse:
        plan = BillingPlanDocument(
            name=payload.name,
            description=payload.description,
            features=payload.features,
            price=_money(payload.price),
            cycle=payload.cycle,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
            trial_days=payload.trial_days,
        )
        await self._repo.plans.create(plan)
        return self._plan_response(plan)

    async def get_plan(self, plan_id: UUID) -> BillingPlanResponse:
        plan = await self._repo.plans.get(plan_id)
        if plan is None:
            raise NotFoundError("Plano não encontrado.", code="plan_not_found")
        return self._plan_response(plan)

    async def update_plan(self, plan_id: UUID, payload: BillingPlanUpdate) -> BillingPlanResponse:
        patch = payload.model_dump(exclude_unset=True)
        if "cycle" in patch and patch["cycle"] is not None:
            patch["cycle"] = getattr(patch["cycle"], "value", patch["cycle"])
        if "price" in patch and patch["price"] is not None:
            patch["price"] = _money(patch["price"])
        plan = await self._repo.plans.update(plan_id, patch)
        if plan is None:
            raise NotFoundError("Plano não encontrado.", code="plan_not_found")
        return self._plan_response(plan)

    # ----------------------------------------------------------------- coupons
    async def list_coupons(self, pagination: PaginationParams) -> BillingCouponListResponse:
        items = await self._repo.coupons.list_all(skip=pagination.skip, limit=pagination.limit)
        total = await self._repo.coupons.count()
        return BillingCouponListResponse(
            items=[self._coupon_response(c) for c in items],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def create_coupon(self, payload: BillingCouponCreate) -> BillingCouponResponse:
        existing = await self._repo.coupons.get_by_code(payload.code)
        if existing:
            raise ConflictError("Já existe um cupom com este código.", code="coupon_exists")
        coupon = BillingCouponDocument(
            code=payload.code,
            discount_type=payload.discount_type,
            discount_value=payload.discount_value,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            max_uses=payload.max_uses,
            applicable_plan_ids=payload.applicable_plan_ids,
            is_active=payload.is_active,
        )
        try:
            await self._repo.coupons.create(coupon)
        except DuplicateKeyError as exc:
            raise ConflictError("Já existe um cupom com este código.", code="coupon_exists") from exc
        return self._coupon_response(coupon)

    async def get_coupon(self, coupon_id: UUID) -> BillingCouponResponse:
        coupon = await self._repo.coupons.get(coupon_id)
        if coupon is None:
            raise NotFoundError("Cupom não encontrado.", code="coupon_not_found")
        return self._coupon_response(coupon)

    async def update_coupon(
        self, coupon_id: UUID, payload: BillingCouponUpdate
    ) -> BillingCouponResponse:
        patch = payload.model_dump(
            exclude_unset=True,
            exclude={"clear_valid_from", "clear_valid_until", "clear_max_uses"},
        )
        if payload.clear_valid_from:
            patch["valid_from"] = None
        if payload.clear_valid_until:
            patch["valid_until"] = None
        if payload.clear_max_uses:
            patch["max_uses"] = None
        if "discount_type" in patch and patch["discount_type"] is not None:
            patch["discount_type"] = getattr(
                patch["discount_type"], "value", patch["discount_type"]
            )
        coupon = await self._repo.coupons.update(coupon_id, patch)
        if coupon is None:
            raise NotFoundError("Cupom não encontrado.", code="coupon_not_found")
        return self._coupon_response(coupon)

    async def validate_coupon(
        self, payload: CouponValidateRequest
    ) -> CouponValidateResponse:
        plan = await self._repo.plans.get(payload.plan_id)
        if plan is None or not plan.is_active:
            raise NotFoundError("Plano não encontrado.", code="plan_not_found")
        coupon = await self._load_valid_coupon(payload.code, plan.id)
        discounted = self._apply_discount(plan.price, coupon)
        return CouponValidateResponse(
            code=coupon.code,
            discount_type=coupon.discount_type,
            discount_value=coupon.discount_value,
            original_price=plan.price,
            discounted_price=discounted,
        )

    async def _load_valid_coupon(self, code: str, plan_id: UUID) -> BillingCouponDocument:
        coupon = await self._repo.coupons.get_by_code(code)
        if coupon is None or not coupon.is_active:
            raise ValidationAppError("Cupom inválido.", code="coupon_invalid")
        now = utcnow()
        if coupon.valid_from and now < coupon.valid_from:
            raise ValidationAppError("Cupom ainda não está válido.", code="coupon_not_started")
        if coupon.valid_until and now > coupon.valid_until:
            raise ValidationAppError("Cupom expirado.", code="coupon_expired")
        if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
            raise ValidationAppError("Cupom esgotado.", code="coupon_exhausted")
        if coupon.applicable_plan_ids and plan_id not in coupon.applicable_plan_ids:
            raise ValidationAppError(
                "Cupom não se aplica a este plano.", code="coupon_plan_mismatch"
            )
        return coupon

    @staticmethod
    def _apply_discount(price: float, coupon: BillingCouponDocument) -> float:
        if coupon.discount_type == CouponDiscountType.PERCENTAGE:
            if coupon.discount_value > 100:
                raise ValidationAppError(
                    "Desconto percentual inválido.", code="coupon_invalid"
                )
            return _money(max(0.0, price * (1 - coupon.discount_value / 100)))
        return _money(max(0.0, price - coupon.discount_value))

    # ---------------------------------------------------------- client billing
    async def get_me(self, *, firebase_uid: str, is_admin: bool) -> BillingMeResponse:
        settings = await self._repo.settings.get_or_create()
        if is_admin:
            return BillingMeResponse(
                status=SubscriptionStatus.ACTIVE,
                has_access=True,
                is_admin=True,
                trial_enabled=settings.trial_enabled,
                trial_days=settings.default_trial_days,
                allowed_billing_types=settings.allowed_billing_types,
            )
        user = await self._resolve_user(firebase_uid)
        company = await self._resolve_company(user)
        subscription = None
        if company:
            subscription = await self._repo.subscriptions.get_open_for_company(company.id)
            if subscription and subscription.status == SubscriptionStatus.PENDING:
                subscription = await self._refresh_pending_from_asaas(subscription)
        status = subscription.status if subscription else SubscriptionStatus.PENDING
        has_access = self._has_access(subscription, settings)
        plan_name = None
        if subscription:
            plan = await self._repo.plans.get(subscription.plan_id)
            plan_name = plan.name if plan else None
        return BillingMeResponse(
            status=status,
            has_access=has_access,
            is_admin=False,
            company_id=company.id if company else None,
            subscription=(
                self._subscription_response(subscription, plan_name) if subscription else None
            ),
            trial_enabled=settings.trial_enabled,
            trial_days=settings.default_trial_days,
            allowed_billing_types=settings.allowed_billing_types,
        )

    def _has_access(
        self,
        subscription: BillingSubscriptionDocument | None,
        settings: BillingSettingsDocument,
    ) -> bool:
        if subscription is None:
            return False
        if subscription.status in {SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE}:
            return True
        if subscription.status == SubscriptionStatus.PAST_DUE:
            if subscription.past_due_since is None:
                return True
            deadline = subscription.past_due_since + timedelta(days=settings.grace_period_days)
            return utcnow() <= deadline
        return False

    async def assert_access(self, firebase_uid: str, *, is_admin: bool) -> None:
        if is_admin:
            return
        me = await self.get_me(firebase_uid=firebase_uid, is_admin=False)
        if me.has_access:
            return
        raise ForbiddenError(
            "É necessário assinar um plano para continuar.",
            code="subscription_required",
            details={"status": me.status},
        )

    async def subscribe(
        self, payload: SubscribeRequest, *, firebase_uid: str
    ) -> SubscribeResponse:
        user = await self._resolve_user(firebase_uid)
        company = await self._require_company(user)
        settings = await self._repo.settings.get_or_create()
        if payload.billing_type not in settings.allowed_billing_types:
            raise ValidationAppError(
                "Meio de pagamento não disponível.", code="billing_type_not_allowed"
            )
        plan = await self._repo.plans.get(payload.plan_id)
        if plan is None or not plan.is_active:
            raise NotFoundError("Plano não encontrado.", code="plan_not_found")

        existing = await self._repo.subscriptions.get_open_for_company(company.id)
        if existing and existing.status in ACCESS_STATUSES:
            raise ConflictError("A empresa já possui uma assinatura ativa.", code="already_subscribed")
        if existing and existing.status == SubscriptionStatus.PENDING:
            if (
                existing.plan_id == plan.id
                and existing.billing_type == payload.billing_type
                and (existing.checkout_url or existing.invoice_url)
            ):
                existing = await self._refresh_pending_from_asaas(existing)
                return SubscribeResponse(
                    subscription=self._subscription_response(existing, plan.name),
                    checkout_url=existing.checkout_url,
                    invoice_url=existing.invoice_url,
                )
            if existing.asaas_subscription_id:
                try:
                    await self._asaas.delete_subscription(existing.asaas_subscription_id)
                except Exception:
                    logger.warning(
                        "asaas_cancel_pending_failed",
                        subscription_id=str(existing.id),
                    )
            await self._repo.subscriptions.update(
                existing.id,
                {
                    "status": SubscriptionStatus.CANCELLED.value,
                    "cancelled_at": utcnow(),
                },
            )

        coupon: BillingCouponDocument | None = None
        price = _money(plan.price)
        if payload.coupon_code:
            coupon = await self._load_valid_coupon(payload.coupon_code, plan.id)
            price = self._apply_discount(plan.price, coupon)
            if price <= 0:
                raise ValidationAppError(
                    "O valor final da assinatura deve ser maior que zero.",
                    code="price_zero",
                )

        trial_days = 0
        if settings.trial_enabled:
            trial_days = plan.trial_days if plan.trial_days is not None else settings.default_trial_days
        trial_ends_at = utcnow() + timedelta(days=trial_days) if trial_days > 0 else None
        next_due = (utcnow() + timedelta(days=trial_days)).date().isoformat()

        subscription = BillingSubscriptionDocument(
            company_id=company.id,
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.PENDING,
            billing_type=payload.billing_type,
            coupon_code=coupon.code if coupon else None,
            price=price,
            cycle=plan.cycle,
            trial_ends_at=trial_ends_at,
            current_period_end=trial_ends_at,
        )
        try:
            await self._repo.subscriptions.create(subscription)
        except DuplicateKeyError as exc:
            raise ConflictError(
                "Não foi possível iniciar a assinatura. Tente novamente.",
                code="subscription_create_conflict",
            ) from exc

        customer_id = await self._ensure_asaas_customer(company, user)
        await self._repo.subscriptions.update(
            subscription.id, {"asaas_customer_id": customer_id}
        )
        subscription.asaas_customer_id = customer_id

        discount_payload = None
        if coupon:
            discount_payload = {
                "value": coupon.discount_value,
                "dueDateLimitDays": 0,
                "type": coupon.discount_type.value,
            }
        fine_payload = {"value": settings.fine_value, "type": settings.fine_type.value}
        interest_payload = {"value": settings.interest_value}

        asaas_sub = await self._create_asaas_subscription(
            customer_id=customer_id,
            subscription=subscription,
            plan=plan,
            next_due=next_due,
            discount=discount_payload,
            fine=fine_payload,
            interest=interest_payload,
        )
        asaas_id = str(asaas_sub.get("id") or "")
        status = SubscriptionStatus.TRIALING if trial_days > 0 else SubscriptionStatus.PENDING
        patch: dict[str, Any] = {
            "asaas_subscription_id": asaas_id,
            "status": status.value,
        }
        invoice_url = await self._sync_invoices(subscription, asaas_id)
        if invoice_url:
            patch["invoice_url"] = invoice_url
        updated = await self._repo.subscriptions.update(subscription.id, patch)
        subscription = updated or subscription
        if coupon:
            await self._repo.coupons.increment_used(coupon.id)
        return SubscribeResponse(
            subscription=self._subscription_response(subscription, plan.name),
            checkout_url=None,
            invoice_url=invoice_url,
        )

    async def get_subscription(self, *, firebase_uid: str) -> BillingSubscriptionResponse:
        user = await self._resolve_user(firebase_uid)
        company = await self._require_company(user)
        subscription = await self._repo.subscriptions.get_open_for_company(company.id)
        if subscription is None:
            raise NotFoundError("Nenhuma assinatura encontrada.", code="subscription_not_found")
        plan = await self._repo.plans.get(subscription.plan_id)
        return self._subscription_response(subscription, plan.name if plan else None)

    async def cancel_subscription(self, *, firebase_uid: str) -> BillingSubscriptionResponse:
        user = await self._resolve_user(firebase_uid)
        company = await self._require_company(user)
        subscription = await self._repo.subscriptions.get_open_for_company(company.id)
        if subscription is None:
            raise NotFoundError("Nenhuma assinatura encontrada.", code="subscription_not_found")
        if subscription.status == SubscriptionStatus.CANCELLED:
            raise ConflictError("Assinatura já cancelada.", code="already_cancelled")
        if subscription.asaas_subscription_id:
            try:
                await self._asaas.delete_subscription(subscription.asaas_subscription_id)
            except Exception:
                logger.warning(
                    "asaas_cancel_failed",
                    subscription_id=str(subscription.id),
                )
                raise
        updated = await self._repo.subscriptions.update(
            subscription.id,
            {
                "status": SubscriptionStatus.CANCELLED.value,
                "cancelled_at": utcnow(),
            },
        )
        subscription = updated or subscription
        plan = await self._repo.plans.get(subscription.plan_id)
        return self._subscription_response(subscription, plan.name if plan else None)

    async def list_invoices(
        self, pagination: PaginationParams, *, firebase_uid: str
    ) -> BillingInvoiceListResponse:
        user = await self._resolve_user(firebase_uid)
        company = await self._require_company(user)
        items = await self._repo.invoices.list_for_company(
            company.id, skip=pagination.skip, limit=pagination.limit
        )
        total = await self._repo.invoices.count_for_company(company.id)
        return BillingInvoiceListResponse(
            items=[self._invoice_response(i) for i in items],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    # ----------------------------------------------------------------- admin
    async def admin_list_subscriptions(
        self, params: AdminSubscriptionListParams
    ) -> AdminSubscriptionListResponse:
        if params.status is None:
            statuses = list(OPEN_SUBSCRIPTION_STATUSES)
        else:
            statuses = [params.status]
        items = await self._repo.subscriptions.list_by_status(
            statuses=statuses, skip=params.skip, limit=params.page_size
        )
        total = await self._repo.subscriptions.count_by_status(statuses)
        return AdminSubscriptionListResponse(
            items=await self._admin_subscription_items(items),
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def admin_get_subscription(self, subscription_id: UUID) -> AdminSubscriptionListItem:
        subscription = await self._repo.subscriptions.get(subscription_id)
        if subscription is None:
            raise NotFoundError("Assinatura não encontrada.", code="subscription_not_found")
        items = await self._admin_subscription_items([subscription])
        return items[0]

    async def admin_list_subscription_invoices(
        self, subscription_id: UUID, pagination: PaginationParams
    ) -> BillingInvoiceListResponse:
        subscription = await self._repo.subscriptions.get(subscription_id)
        if subscription is None:
            raise NotFoundError("Assinatura não encontrada.", code="subscription_not_found")
        items = await self._repo.invoices.list_for_subscription(
            subscription_id, skip=pagination.skip, limit=pagination.limit
        )
        total = await self._repo.invoices.count_for_subscription(subscription_id)
        return BillingInvoiceListResponse(
            items=[self._invoice_response(i) for i in items],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def admin_list_pending_users(
        self, pagination: PaginationParams
    ) -> AdminPendingUserListResponse:
        subscribed_ids = await self._repo.subscriptions.company_ids_with_access()
        companies = await self._companies_repo.list_active_except(
            subscribed_ids, skip=pagination.skip, limit=pagination.limit
        )
        total = await self._companies_repo.count_active_except(subscribed_ids)
        owners = await self._auth_repo.get_by_ids([c.owner_user_id for c in companies])
        owners_map = {u.id: u for u in owners}
        items = [
            AdminPendingUserItem(
                user_id=company.owner_user_id,
                user_name=owners_map.get(company.owner_user_id).name
                if owners_map.get(company.owner_user_id)
                else None,
                user_email=str(owners_map.get(company.owner_user_id).email)
                if owners_map.get(company.owner_user_id)
                and owners_map[company.owner_user_id].email
                else None,
                company_id=company.id,
                company_name=company.trade_name or company.legal_name,
                created_at=company.created_at,
            )
            for company in companies
        ]
        return AdminPendingUserListResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def _admin_subscription_items(
        self, subscriptions: list[BillingSubscriptionDocument]
    ) -> list[AdminSubscriptionListItem]:
        plan_map = await self._repo.plans.get_many([s.plan_id for s in subscriptions])
        company_map = await self._companies_repo.get_many([s.company_id for s in subscriptions])
        users = await self._auth_repo.get_by_ids(
            [s.user_id for s in subscriptions], active_only=False
        )
        user_map = {u.id: u for u in users}
        items: list[AdminSubscriptionListItem] = []
        for sub in subscriptions:
            company = company_map.get(sub.company_id)
            user = user_map.get(sub.user_id)
            plan = plan_map.get(sub.plan_id)
            items.append(
                AdminSubscriptionListItem(
                    id=sub.id,
                    company_id=sub.company_id,
                    company_name=(company.trade_name or company.legal_name) if company else None,
                    user_id=sub.user_id,
                    user_name=user.name if user else None,
                    user_email=str(user.email) if user and user.email else None,
                    plan_id=sub.plan_id,
                    plan_name=plan.name if plan else None,
                    status=sub.status,
                    billing_type=sub.billing_type,
                    price=sub.price,
                    cycle=sub.cycle,
                    coupon_code=sub.coupon_code,
                    trial_ends_at=sub.trial_ends_at,
                    current_period_end=sub.current_period_end,
                    cancelled_at=sub.cancelled_at,
                    created_at=sub.created_at,
                )
            )
        return items

    # ---------------------------------------------------------------- webhooks
    async def handle_webhook(self, payload: dict[str, Any], token: str | None) -> MessageResponse:
        settings = get_settings()
        expected = settings.ASAAS_WEBHOOK_TOKEN.strip()
        event_id = str(payload.get("id") or "")
        event = str(payload.get("event") or payload.get("type") or "")
        if not expected or token != expected:
            raise ForbiddenError("Webhook token inválido.", code="webhook_unauthorized")
        if not event_id or not event:
            raise ValidationAppError("Payload de webhook inválido.", code="webhook_invalid")
        first_time = await self._repo.webhook_events.try_record(event_id, event)
        if not first_time:
            return MessageResponse(message="already processed")
        try:
            await self._process_webhook_event(event, payload)
        except Exception:
            logger.exception("billing_webhook_failed", event=event, event_id=event_id)
            await self._repo.webhook_events.delete_by_event_id(event_id)
            raise
        return MessageResponse(message="ok")

    async def _process_webhook_event(self, event: str, payload: dict[str, Any]) -> None:
        if event.startswith("PAYMENT_"):
            payment = payload.get("payment") or {}
            if isinstance(payment, dict):
                await self._handle_payment_event(event, payment)
            return
        if event.startswith("SUBSCRIPTION_"):
            subscription = payload.get("subscription") or {}
            if isinstance(subscription, dict):
                await self._handle_subscription_event(event, subscription)
            return
        if event.startswith("CHECKOUT_"):
            checkout = payload.get("checkout") or {}
            if isinstance(checkout, dict):
                await self._handle_checkout_event(event, checkout)

    async def _handle_payment_event(self, event: str, payment: dict[str, Any]) -> None:
        asaas_sub_id = payment.get("subscription")
        local = None
        if isinstance(asaas_sub_id, str) and asaas_sub_id:
            local = await self._repo.subscriptions.get_by_asaas_subscription_id(asaas_sub_id)
        if local is None:
            ref = payment.get("externalReference")
            if isinstance(ref, str):
                local = await self._repo.subscriptions.get_by_external_reference(ref)
        if local is None:
            logger.info("billing_payment_unmatched", event=event)
            return
        await self._upsert_invoice(local, payment)
        asaas_status = str(payment.get("status") or "").upper()
        patch: dict[str, Any] = {}
        if event in {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"} or asaas_status in {
            "CONFIRMED",
            "RECEIVED",
            "RECEIVED_IN_CASH",
        }:
            if local.status != SubscriptionStatus.CANCELLED:
                patch["status"] = SubscriptionStatus.ACTIVE.value
                patch["past_due_since"] = None
                due = _parse_asaas_datetime(payment.get("dueDate"))
                if due:
                    patch["current_period_end"] = due
        elif event == "PAYMENT_OVERDUE" or asaas_status == "OVERDUE":
            if local.status not in {SubscriptionStatus.CANCELLED}:
                patch["status"] = SubscriptionStatus.PAST_DUE.value
                if local.past_due_since is None:
                    patch["past_due_since"] = utcnow()
        elif event == "PAYMENT_DELETED":
            return
        if patch:
            await self._repo.subscriptions.update(local.id, patch)

    async def _handle_subscription_event(self, event: str, payload: dict[str, Any]) -> None:
        asaas_id = str(payload.get("id") or "")
        local = None
        if asaas_id:
            local = await self._repo.subscriptions.get_by_asaas_subscription_id(asaas_id)
        if local is None:
            ref = payload.get("externalReference")
            if isinstance(ref, str):
                local = await self._repo.subscriptions.get_by_external_reference(ref)
        if local is None:
            logger.info("billing_subscription_unmatched", event=event)
            return
        patch: dict[str, Any] = {}
        if asaas_id and not local.asaas_subscription_id:
            patch["asaas_subscription_id"] = asaas_id
        if event in {"SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"}:
            patch["status"] = SubscriptionStatus.CANCELLED.value
            patch["cancelled_at"] = utcnow()
        elif event == "SUBSCRIPTION_CREATED" and local.status == SubscriptionStatus.PENDING:
            if local.trial_ends_at and local.trial_ends_at > utcnow():
                patch["status"] = SubscriptionStatus.TRIALING.value
            else:
                patch["status"] = SubscriptionStatus.PENDING.value
        next_due = _parse_asaas_datetime(payload.get("nextDueDate"))
        if next_due:
            patch["current_period_end"] = next_due
        if patch:
            await self._repo.subscriptions.update(local.id, patch)
        if asaas_id:
            await self._sync_invoices(local, asaas_id)

    async def _handle_checkout_event(self, event: str, payload: dict[str, Any]) -> None:
        checkout_id = str(payload.get("id") or "")
        local = None
        if checkout_id:
            local = await self._repo.subscriptions.get_by_asaas_checkout_id(checkout_id)
        if local is None:
            ref = payload.get("externalReference")
            if isinstance(ref, str):
                local = await self._repo.subscriptions.get_by_external_reference(ref)
        if local is None:
            return
        if event in {"CHECKOUT_CANCELED", "CHECKOUT_EXPIRED"}:
            if local.status == SubscriptionStatus.PENDING:
                await self._repo.subscriptions.update(
                    local.id,
                    {
                        "status": SubscriptionStatus.CANCELLED.value,
                        "cancelled_at": utcnow(),
                    },
                )
            return
        if event == "CHECKOUT_PAID" and local.status == SubscriptionStatus.PENDING:
            status = (
                SubscriptionStatus.TRIALING
                if local.trial_ends_at and local.trial_ends_at > utcnow()
                else SubscriptionStatus.ACTIVE
            )
            await self._repo.subscriptions.update(local.id, {"status": status.value})

    # ------------------------------------------------------------- Asaas IO
    async def _ensure_asaas_customer(
        self, company: CompanyDocument, user: UserDocument
    ) -> str:
        tax_id = _digits(company.tax_id)
        existing = await self._asaas.find_customer_by_tax_id(tax_id)
        if existing and existing.get("id"):
            return str(existing["id"])
        address = company.address
        phone = _digits(company.phone or user.phone)
        payload: dict[str, Any] = {
            "name": company.legal_name,
            "cpfCnpj": tax_id,
            "email": company.email or user.email,
            "externalReference": str(company.id),
            "notificationDisabled": False,
        }
        if phone:
            payload["phone"] = phone
            payload["mobilePhone"] = phone
        if address:
            postal = _digits(address.postal_code)
            if postal:
                payload["postalCode"] = postal
            if address.street:
                payload["address"] = address.street
            if address.number:
                payload["addressNumber"] = address.number
            if address.complement:
                payload["complement"] = address.complement
            if address.neighborhood:
                payload["province"] = address.neighborhood
        created = await self._asaas.create_customer(payload)
        customer_id = created.get("id")
        if not customer_id:
            raise ValidationAppError(
                "Não foi possível cadastrar o cliente no provedor de pagamentos.",
                code="asaas_customer_failed",
            )
        return str(customer_id)

    async def _create_asaas_subscription(
        self,
        *,
        customer_id: str,
        subscription: BillingSubscriptionDocument,
        plan: BillingPlanDocument,
        next_due: str,
        discount: dict[str, Any] | None,
        fine: dict[str, Any],
        interest: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "customer": customer_id,
            "billingType": subscription.billing_type.value,
            "value": subscription.price,
            "nextDueDate": next_due,
            "cycle": plan.cycle.value,
            "description": f"Econmesh — {plan.name}",
            "externalReference": str(subscription.id),
            "fine": fine,
            "interest": interest,
        }
        if discount:
            payload["discount"] = discount
        return await self._asaas.create_subscription(payload)

    async def _refresh_pending_from_asaas(
        self, subscription: BillingSubscriptionDocument
    ) -> BillingSubscriptionDocument:
        if subscription.status != SubscriptionStatus.PENDING:
            return subscription
        if not subscription.asaas_subscription_id:
            return subscription
        try:
            payments = await self._asaas.list_subscription_payments(
                subscription.asaas_subscription_id
            )
        except Exception:
            logger.warning(
                "asaas_refresh_pending_failed", subscription_id=str(subscription.id)
            )
            return subscription
        paid = False
        invoice_url = subscription.invoice_url
        for payment in payments:
            invoice = await self._upsert_invoice(subscription, payment)
            asaas_status = str(payment.get("status") or "").upper()
            if invoice and invoice.invoice_url and not invoice_url:
                invoice_url = invoice.invoice_url
            if asaas_status in {"CONFIRMED", "RECEIVED", "RECEIVED_IN_CASH"}:
                paid = True
        patch: dict[str, Any] = {}
        if invoice_url and invoice_url != subscription.invoice_url:
            patch["invoice_url"] = invoice_url
        if paid:
            patch["status"] = SubscriptionStatus.ACTIVE.value
            patch["past_due_since"] = None
        if patch:
            updated = await self._repo.subscriptions.update(subscription.id, patch)
            subscription = updated or subscription
        return subscription

    async def _sync_invoices(
        self, subscription: BillingSubscriptionDocument, asaas_subscription_id: str
    ) -> str | None:
        try:
            payments = await self._asaas.list_subscription_payments(asaas_subscription_id)
        except Exception:
            logger.warning("asaas_list_payments_failed", subscription_id=str(subscription.id))
            return subscription.invoice_url
        first_url: str | None = None
        for payment in payments:
            invoice = await self._upsert_invoice(subscription, payment)
            if invoice and first_url is None and invoice.invoice_url:
                first_url = invoice.invoice_url
        return first_url or subscription.invoice_url

    async def _upsert_invoice(
        self, subscription: BillingSubscriptionDocument, payment: dict[str, Any]
    ) -> BillingInvoiceDocument | None:
        payment_id = str(payment.get("id") or "")
        if not payment_id:
            logger.info("billing_payment_missing_id")
            return None
        asaas_status = str(payment.get("status") or "")
        invoice = BillingInvoiceDocument(
            subscription_id=subscription.id,
            company_id=subscription.company_id,
            asaas_payment_id=payment_id,
            asaas_subscription_id=payment.get("subscription"),
            value=float(payment.get("value") or subscription.price),
            due_date=_parse_asaas_datetime(payment.get("dueDate")),
            status=_ASAAS_INVOICE_STATUS.get(asaas_status.upper(), InvoiceStatus.OTHER),
            asaas_status=asaas_status or None,
            billing_type=payment.get("billingType"),
            invoice_url=payment.get("invoiceUrl"),
            bank_slip_url=payment.get("bankSlipUrl"),
            paid_at=_parse_asaas_datetime(
                payment.get("paymentDate") or payment.get("confirmedDate")
            ),
        )
        if (
            str(payment.get("billingType") or "").upper() == "PIX"
            and payment_id
            and not invoice.pix_copy_paste
        ):
            try:
                pix = await self._asaas.get_pix_qr_code(payment_id)
                invoice.pix_qr_code = pix.get("encodedImage")
                invoice.pix_copy_paste = pix.get("payload")
            except Exception:
                logger.info("asaas_pix_qr_skipped", payment_id=payment_id)
        return await self._repo.invoices.upsert_from_asaas(invoice)

    # ------------------------------------------------------------- responses
    @staticmethod
    def _plan_response(plan: BillingPlanDocument) -> BillingPlanResponse:
        return BillingPlanResponse(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            features=plan.features,
            price=plan.price,
            cycle=plan.cycle,
            is_active=plan.is_active,
            sort_order=plan.sort_order,
            trial_days=plan.trial_days,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    @staticmethod
    def _settings_response(settings: BillingSettingsDocument) -> BillingSettingsResponse:
        return BillingSettingsResponse(
            id=settings.id,
            trial_enabled=settings.trial_enabled,
            default_trial_days=settings.default_trial_days,
            allowed_billing_types=settings.allowed_billing_types,
            fine_value=settings.fine_value,
            fine_type=settings.fine_type,
            interest_value=settings.interest_value,
            grace_period_days=settings.grace_period_days,
            updated_at=settings.updated_at,
        )

    @staticmethod
    def _coupon_response(coupon: BillingCouponDocument) -> BillingCouponResponse:
        return BillingCouponResponse(
            id=coupon.id,
            code=coupon.code,
            discount_type=coupon.discount_type,
            discount_value=coupon.discount_value,
            valid_from=coupon.valid_from,
            valid_until=coupon.valid_until,
            max_uses=coupon.max_uses,
            used_count=coupon.used_count,
            applicable_plan_ids=coupon.applicable_plan_ids,
            is_active=coupon.is_active,
            created_at=coupon.created_at,
            updated_at=coupon.updated_at,
        )

    @staticmethod
    def _subscription_response(
        subscription: BillingSubscriptionDocument, plan_name: str | None
    ) -> BillingSubscriptionResponse:
        return BillingSubscriptionResponse(
            id=subscription.id,
            company_id=subscription.company_id,
            user_id=subscription.user_id,
            plan_id=subscription.plan_id,
            plan_name=plan_name,
            status=subscription.status,
            billing_type=subscription.billing_type,
            coupon_code=subscription.coupon_code,
            price=subscription.price,
            cycle=subscription.cycle,
            checkout_url=subscription.checkout_url,
            invoice_url=subscription.invoice_url,
            trial_ends_at=subscription.trial_ends_at,
            current_period_end=subscription.current_period_end,
            cancelled_at=subscription.cancelled_at,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    @staticmethod
    def _invoice_response(invoice: BillingInvoiceDocument) -> BillingInvoiceResponse:
        return BillingInvoiceResponse(
            id=invoice.id,
            subscription_id=invoice.subscription_id,
            value=invoice.value,
            due_date=invoice.due_date,
            status=invoice.status,
            asaas_status=invoice.asaas_status,
            billing_type=invoice.billing_type,
            invoice_url=invoice.invoice_url,
            bank_slip_url=invoice.bank_slip_url,
            pix_qr_code=invoice.pix_qr_code,
            pix_copy_paste=invoice.pix_copy_paste,
            paid_at=invoice.paid_at,
            created_at=invoice.created_at,
        )


__all__ = ["BillingService"]
