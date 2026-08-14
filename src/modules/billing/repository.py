"""Mongo repositories for billing collections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.modules.billing.model import (
    BILLING_SETTINGS_ID,
    BillingCouponDocument,
    BillingInvoiceDocument,
    BillingPlanDocument,
    BillingSettingsDocument,
    BillingSubscriptionDocument,
    BillingWebhookEventDocument,
    OPEN_SUBSCRIPTION_STATUSES,
    SubscriptionStatus,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class BillingPlansRepository:
    COLLECTION: str = BillingPlanDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("is_active", ASCENDING), ("sort_order", ASCENDING)],
            name="ix_plans_active_sort",
        )

    async def create(self, plan: BillingPlanDocument) -> BillingPlanDocument:
        await self._collection.insert_one(plan.to_mongo())
        return plan

    async def get(self, plan_id: UUID) -> BillingPlanDocument | None:
        doc = await self._collection.find_one({"_id": plan_id})
        return BillingPlanDocument.model_validate(doc) if doc else None

    async def update(self, plan_id: UUID, patch: dict[str, Any]) -> BillingPlanDocument | None:
        patch = {**patch, "updated_at": utcnow()}
        doc = await self._collection.find_one_and_update(
            {"_id": plan_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return BillingPlanDocument.model_validate(doc) if doc else None

    async def list_all(
        self, *, skip: int, limit: int, active_only: bool = False
    ) -> list[BillingPlanDocument]:
        query: dict[str, Any] = {"is_active": True} if active_only else {}
        cursor = (
            self._collection.find(query)
            .sort([("sort_order", ASCENDING), ("created_at", ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BillingPlanDocument.model_validate(d) for d in docs]

    async def count(self, *, active_only: bool = False) -> int:
        query: dict[str, Any] = {"is_active": True} if active_only else {}
        return await self._collection.count_documents(query)

    async def get_many(self, plan_ids: list[UUID]) -> dict[UUID, BillingPlanDocument]:
        if not plan_ids:
            return {}
        cursor = self._collection.find({"_id": {"$in": plan_ids}})
        docs = await cursor.to_list(length=len(plan_ids))
        plans = [BillingPlanDocument.model_validate(d) for d in docs]
        return {p.id: p for p in plans}


class BillingSettingsRepository:
    COLLECTION: str = BillingSettingsDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        return None

    async def get_or_create(self) -> BillingSettingsDocument:
        doc = await self._collection.find_one({"_id": BILLING_SETTINGS_ID})
        if doc:
            return BillingSettingsDocument.model_validate(doc)
        settings = BillingSettingsDocument()
        try:
            await self._collection.insert_one(settings.to_mongo())
        except DuplicateKeyError:
            existing = await self._collection.find_one({"_id": BILLING_SETTINGS_ID})
            if existing:
                return BillingSettingsDocument.model_validate(existing)
            raise
        return settings

    async def update(self, patch: dict[str, Any]) -> BillingSettingsDocument:
        await self.get_or_create()
        patch = {**patch, "updated_at": utcnow()}
        doc = await self._collection.find_one_and_update(
            {"_id": BILLING_SETTINGS_ID},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return await self.get_or_create()
        return BillingSettingsDocument.model_validate(doc)


class BillingCouponsRepository:
    COLLECTION: str = BillingCouponDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("code", ASCENDING)], unique=True, name="ux_coupon_code"
        )

    async def create(self, coupon: BillingCouponDocument) -> BillingCouponDocument:
        await self._collection.insert_one(coupon.to_mongo())
        return coupon

    async def get(self, coupon_id: UUID) -> BillingCouponDocument | None:
        doc = await self._collection.find_one({"_id": coupon_id})
        return BillingCouponDocument.model_validate(doc) if doc else None

    async def get_by_code(self, code: str) -> BillingCouponDocument | None:
        doc = await self._collection.find_one({"code": code.upper()})
        return BillingCouponDocument.model_validate(doc) if doc else None

    async def update(
        self, coupon_id: UUID, patch: dict[str, Any]
    ) -> BillingCouponDocument | None:
        patch = {**patch, "updated_at": utcnow()}
        doc = await self._collection.find_one_and_update(
            {"_id": coupon_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return BillingCouponDocument.model_validate(doc) if doc else None

    async def increment_used(self, coupon_id: UUID) -> None:
        await self._collection.update_one(
            {"_id": coupon_id},
            {"$inc": {"used_count": 1}, "$set": {"updated_at": utcnow()}},
        )

    async def list_all(self, *, skip: int, limit: int) -> list[BillingCouponDocument]:
        cursor = (
            self._collection.find({})
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BillingCouponDocument.model_validate(d) for d in docs]

    async def count(self) -> int:
        return await self._collection.count_documents({})


class BillingSubscriptionsRepository:
    COLLECTION: str = BillingSubscriptionDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("company_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            name="ix_sub_company_status",
        )
        for field, name in (
            ("asaas_subscription_id", "ux_asaas_subscription_id"),
            ("asaas_checkout_id", "ux_asaas_checkout_id"),
        ):
            try:
                await self._collection.drop_index(name)
            except Exception:  # noqa: BLE001
                pass
            await self._collection.create_index(
                [(field, ASCENDING)],
                unique=True,
                partialFilterExpression={field: {"$type": "string"}},
                name=name,
            )
        await self._collection.create_index(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            name="ix_sub_status_created",
        )

    async def create(
        self, sub: BillingSubscriptionDocument
    ) -> BillingSubscriptionDocument:
        payload = sub.to_mongo()
        for key in ("asaas_subscription_id", "asaas_checkout_id"):
            if payload.get(key) is None:
                payload.pop(key, None)
        await self._collection.insert_one(payload)
        return sub

    async def get(self, subscription_id: UUID) -> BillingSubscriptionDocument | None:
        doc = await self._collection.find_one({"_id": subscription_id})
        return BillingSubscriptionDocument.model_validate(doc) if doc else None

    async def get_open_for_company(
        self, company_id: UUID
    ) -> BillingSubscriptionDocument | None:
        statuses = [s.value for s in OPEN_SUBSCRIPTION_STATUSES]
        doc = await self._collection.find_one(
            {"company_id": company_id, "status": {"$in": statuses}},
            sort=[("created_at", DESCENDING)],
        )
        return BillingSubscriptionDocument.model_validate(doc) if doc else None

    async def get_by_asaas_subscription_id(
        self, asaas_id: str
    ) -> BillingSubscriptionDocument | None:
        doc = await self._collection.find_one({"asaas_subscription_id": asaas_id})
        return BillingSubscriptionDocument.model_validate(doc) if doc else None

    async def get_by_asaas_checkout_id(
        self, checkout_id: str
    ) -> BillingSubscriptionDocument | None:
        doc = await self._collection.find_one({"asaas_checkout_id": checkout_id})
        return BillingSubscriptionDocument.model_validate(doc) if doc else None

    async def get_by_external_reference(
        self, reference: str
    ) -> BillingSubscriptionDocument | None:
        try:
            sub_id = UUID(reference)
        except ValueError:
            return None
        return await self.get(sub_id)

    async def update(
        self, subscription_id: UUID, patch: dict[str, Any]
    ) -> BillingSubscriptionDocument | None:
        patch = {**patch, "updated_at": utcnow()}
        doc = await self._collection.find_one_and_update(
            {"_id": subscription_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return BillingSubscriptionDocument.model_validate(doc) if doc else None

    async def list_by_status(
        self,
        *,
        statuses: list[SubscriptionStatus],
        skip: int,
        limit: int,
    ) -> list[BillingSubscriptionDocument]:
        query = {"status": {"$in": [getattr(s, "value", s) for s in statuses]}}
        cursor = (
            self._collection.find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BillingSubscriptionDocument.model_validate(d) for d in docs]

    async def count_by_status(self, statuses: list[SubscriptionStatus]) -> int:
        return await self._collection.count_documents(
            {"status": {"$in": [getattr(s, "value", s) for s in statuses]}}
        )

    async def company_ids_with_access(self) -> set[UUID]:
        cursor = self._collection.find(
            {
                "status": {
                    "$in": [
                        SubscriptionStatus.TRIALING.value,
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.PAST_DUE.value,
                    ]
                }
            },
            projection={"company_id": 1},
        )
        docs = await cursor.to_list(length=None)
        return {doc["company_id"] for doc in docs}


class BillingInvoicesRepository:
    COLLECTION: str = BillingInvoiceDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("asaas_payment_id", ASCENDING)],
            unique=True,
            name="ux_asaas_payment_id",
        )
        await self._collection.create_index(
            [("subscription_id", ASCENDING), ("due_date", DESCENDING)],
            name="ix_invoice_subscription_due",
        )
        await self._collection.create_index(
            [("company_id", ASCENDING), ("due_date", DESCENDING)],
            name="ix_invoice_company_due",
        )

    async def upsert_from_asaas(
        self, invoice: BillingInvoiceDocument
    ) -> BillingInvoiceDocument:
        now = utcnow()
        payload = invoice.to_mongo()
        payload.pop("_id", None)
        payload.pop("created_at", None)
        payload["updated_at"] = now
        doc = await self._collection.find_one_and_update(
            {"asaas_payment_id": invoice.asaas_payment_id},
            {
                "$set": payload,
                "$setOnInsert": {"_id": invoice.id, "created_at": invoice.created_at},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return BillingInvoiceDocument.model_validate(doc)

    async def list_for_subscription(
        self, subscription_id: UUID, *, skip: int, limit: int
    ) -> list[BillingInvoiceDocument]:
        cursor = (
            self._collection.find({"subscription_id": subscription_id})
            .sort("due_date", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BillingInvoiceDocument.model_validate(d) for d in docs]

    async def count_for_subscription(self, subscription_id: UUID) -> int:
        return await self._collection.count_documents({"subscription_id": subscription_id})

    async def list_for_company(
        self, company_id: UUID, *, skip: int, limit: int
    ) -> list[BillingInvoiceDocument]:
        cursor = (
            self._collection.find({"company_id": company_id})
            .sort("due_date", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BillingInvoiceDocument.model_validate(d) for d in docs]

    async def count_for_company(self, company_id: UUID) -> int:
        return await self._collection.count_documents({"company_id": company_id})


class BillingWebhookEventsRepository:
    COLLECTION: str = BillingWebhookEventDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("asaas_event_id", ASCENDING)],
            unique=True,
            name="ux_asaas_event_id",
        )

    async def try_record(self, asaas_event_id: str, event: str) -> bool:
        """Return True if this is the first time we see the event."""
        doc = BillingWebhookEventDocument(asaas_event_id=asaas_event_id, event=event)
        try:
            await self._collection.insert_one(doc.to_mongo())
            return True
        except DuplicateKeyError:
            return False

    async def delete_by_event_id(self, asaas_event_id: str) -> None:
        await self._collection.delete_one({"asaas_event_id": asaas_event_id})


class BillingRepository:
    """Facade that groups billing collections for DI."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.plans = BillingPlansRepository(db)
        self.settings = BillingSettingsRepository(db)
        self.coupons = BillingCouponsRepository(db)
        self.subscriptions = BillingSubscriptionsRepository(db)
        self.invoices = BillingInvoicesRepository(db)
        self.webhook_events = BillingWebhookEventsRepository(db)

    async def ensure_indexes(self) -> None:
        await self.plans.ensure_indexes()
        await self.settings.ensure_indexes()
        await self.coupons.ensure_indexes()
        await self.subscriptions.ensure_indexes()
        await self.invoices.ensure_indexes()
        await self.webhook_events.ensure_indexes()


__all__ = [
    "BillingCouponsRepository",
    "BillingInvoicesRepository",
    "BillingPlansRepository",
    "BillingRepository",
    "BillingSettingsRepository",
    "BillingSubscriptionsRepository",
    "BillingWebhookEventsRepository",
]
