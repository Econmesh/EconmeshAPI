"""Smoke tests for the health endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.unit


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": None}


async def test_readiness_includes_dependency_checks(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "mongo" in body["checks"]
    assert "redis" in body["checks"]


async def test_request_id_header_is_returned(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.headers.get("X-Request-ID")
    assert response.headers.get("X-Trace-ID")
