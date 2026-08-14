"""Public Asaas webhook endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status

from src.modules.billing.controller import BillingWebhookController
from src.modules.billing.deps import build_billing_webhook_controller
from src.shared.dependencies.db import get_db
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/billing/webhooks", tags=["billing-webhooks"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> BillingWebhookController:
    return build_billing_webhook_controller(db)


ControllerDep = Annotated[BillingWebhookController, Depends(_build_controller)]


@router.post(
    "/asaas",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive Asaas billing webhooks.",
)
async def asaas_webhook(
    request: Request,
    controller: ControllerDep,
    asaas_access_token: Annotated[str | None, Header(alias="asaas-access-token")] = None,
) -> MessageResponse:
    payload: dict[str, Any] = await request.json()
    if not isinstance(payload, dict):
        payload = {}
    return await controller.handle(payload, asaas_access_token)


__all__ = ["router"]
