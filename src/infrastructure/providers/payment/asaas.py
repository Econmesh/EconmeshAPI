"""Asaas HTTP client. Card data never transits through this layer."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from src.core.config import Settings, get_settings
from src.core.exceptions import ExternalServiceError, ValidationAppError
from src.core.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class AsaasClientError(ExternalServiceError):
    code = "asaas_error"
    message = "Falha ao comunicar com o provedor de pagamentos."


class AsaasPaymentProvider:
    """Thin async wrapper around the Asaas REST API (v3)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self._settings.ASAAS_API_KEY.strip())

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ValidationAppError(
                "Pagamentos não estão configurados. Contate o suporte.",
                code="billing_not_configured",
            )

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "access_token": self._settings.ASAAS_API_KEY,
            "User-Agent": f"{self._settings.APP_NAME}/{self._settings.APP_VERSION}",
        }

    def _base_url(self) -> str:
        raw = self._settings.ASAAS_API_URL.strip().rstrip("/")
        if not raw:
            return "https://api-sandbox.asaas.com/v3"
        parsed = urlparse(raw)
        path = (parsed.path or "").rstrip("/")
        if path.endswith("/v3"):
            return raw
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or raw.removeprefix("https://").removeprefix("http://")
        return f"{scheme}://{netloc}/v3"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        url = f"{self._base_url()}{path}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json,
                    params=params,
                )
        except httpx.TimeoutException as exc:
            logger.warning("asaas_timeout", method=method, path=path)
            raise AsaasClientError(
                "O provedor de pagamentos não respondeu a tempo.",
                code="asaas_timeout",
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("asaas_http_error", method=method, path=path, error=str(exc))
            raise AsaasClientError() from exc

        if response.status_code >= 400:
            payload: dict[str, Any] = {}
            try:
                payload = response.json()
            except ValueError:
                payload = {"raw": response.text[:500]}
            errors = payload.get("errors") if isinstance(payload, dict) else None
            description = "Falha no provedor de pagamentos."
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    description = str(first.get("description") or description)
            logger.warning(
                "asaas_error_response",
                method=method,
                path=path,
                status_code=response.status_code,
            )
            raise AsaasClientError(
                description,
                details={"status_code": response.status_code},
            )

        if response.status_code == 204 or not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}

    async def find_customer_by_tax_id(self, tax_id: str) -> dict[str, Any] | None:
        digits = "".join(ch for ch in tax_id if ch.isdigit())
        try:
            result = await self._request("GET", "/customers", params={"cpfCnpj": digits})
        except AsaasClientError as exc:
            if exc.details.get("status_code") == 404:
                return None
            raise
        items = result.get("data") or []
        if isinstance(items, list) and items:
            first = items[0]
            return first if isinstance(first, dict) else None
        return None

    async def create_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/customers", json=payload)

    async def create_subscription(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/subscriptions", json=payload)

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/subscriptions/{subscription_id}")

    async def delete_subscription(self, subscription_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/subscriptions/{subscription_id}")

    async def list_subscription_payments(self, subscription_id: str) -> list[dict[str, Any]]:
        result = await self._request(
            "GET",
            f"/subscriptions/{subscription_id}/payments",
            params={"limit": 100},
        )
        items = result.get("data") or []
        return [item for item in items if isinstance(item, dict)]

    async def get_pix_qr_code(self, payment_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/payments/{payment_id}/pixQrCode")

    async def create_checkout(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/checkouts", json=payload)


__all__ = ["AsaasClientError", "AsaasPaymentProvider"]
