"""Tests for admin module routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUser, get_current_user

pytestmark = pytest.mark.unit


async def test_admin_users_requires_admin_role(
    app: FastAPI, client: AsyncClient
) -> None:
    async def _override() -> CurrentUser:
        return CurrentUser(
            uid="firebase-viewer",
            email="viewer@example.com",
            role=Role.VIEWER,
            email_verified=True,
        )

    app.dependency_overrides[get_current_user] = _override
    try:
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "role_required"
    finally:
        app.dependency_overrides.clear()


async def test_admin_users_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 401
    assert response.json()["code"] == "missing_token"
