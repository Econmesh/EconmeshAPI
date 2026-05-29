"""Tests for the auth module routes (Firebase is mocked)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.shared.dependencies.auth import CurrentUser, get_current_user

pytestmark = pytest.mark.unit


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "missing_token"


async def test_me_returns_current_user_when_authenticated(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_user = CurrentUser(
        uid="firebase-uid-123",
        email="alice@example.com",
        name="Alice",
        email_verified=True,
    )

    async def _override() -> CurrentUser:
        return fake_user

    app.dependency_overrides[get_current_user] = _override
    try:
        # The route also depends on the AuthController -> service.get_me, which
        # hits Mongo. For a unit test we stub that as well via the controller.
        from src.modules.auth.controller import AuthController
        from src.modules.auth.routes import _build_controller
        from src.modules.auth.schema import MeResponse
        from src.shared.constants.roles import Role
        from src.shared.utils.ids import new_uuid
        from src.shared.utils.time import utcnow

        class _StubController(AuthController):
            def __init__(self) -> None:  # noqa: D401 — test stub
                pass

            async def me(self, current_user: CurrentUser) -> MeResponse:  # type: ignore[override]
                now = utcnow()
                return MeResponse(
                    id=new_uuid(),
                    firebase_uid=current_user.uid,
                    email=current_user.email,
                    name=current_user.name,
                    email_verified=current_user.email_verified,
                    role=Role.VIEWER,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )

        def _build_stub() -> AuthController:
            return _StubController()

        app.dependency_overrides[_build_controller] = _build_stub

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["firebase_uid"] == "firebase-uid-123"
        assert body["email"] == "alice@example.com"
    finally:
        app.dependency_overrides.clear()
