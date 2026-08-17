"""Tests for platform settings routes and service."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from src.modules.platform_settings.admin_routes import _build_service as _build_admin_service
from src.modules.platform_settings.model import (
    PLATFORM_SETTINGS_ID,
    ForoFillMode,
    PlatformSettingsDocument,
)
from src.modules.platform_settings.routes import _build_service
from src.modules.platform_settings.schema import PlatformSettingsResponse
from src.modules.platform_settings.service import PlatformSettingsService
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUser, get_current_user
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> PlatformSettingsDocument:
    data: dict[str, object] = {
        "require_signature_authorization": False,
    }
    data.update(overrides)
    return PlatformSettingsDocument.model_validate(data)


def _response(
    *, require_signature_authorization: bool = False
) -> PlatformSettingsResponse:
    now = utcnow()
    return PlatformSettingsResponse(
        id=PLATFORM_SETTINGS_ID,
        require_signature_authorization=require_signature_authorization,
        foro_fill_mode="company",
        foro_city=None,
        foro_state=None,
        updated_at=now,
    )


async def test_get_platform_settings_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/platform/settings")
    assert response.status_code == 401


async def test_get_platform_settings_returns_defaults(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123", email="alice@example.com")
    payload = _response()

    class _StubService(PlatformSettingsService):
        def __init__(self) -> None:
            pass

        async def get(self) -> PlatformSettingsResponse:
            return payload

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_service] = lambda: _StubService()
    try:
        response = await client.get(
            "/api/v1/platform/settings",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["require_signature_authorization"] is False
        assert body["foro_fill_mode"] == "company"
    finally:
        app.dependency_overrides.clear()


async def test_admin_patch_platform_settings_requires_admin(
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
        response = await client.patch(
            "/api/v1/admin/platform/settings",
            json={"require_signature_authorization": True},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "role_required"
    finally:
        app.dependency_overrides.clear()


async def test_admin_patch_platform_settings_updates_flag(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_admin = CurrentUser(
        uid="firebase-admin",
        email="admin@example.com",
        role=Role.ADMIN,
        email_verified=True,
    )
    payload = _response(require_signature_authorization=True)

    class _StubService(PlatformSettingsService):
        def __init__(self) -> None:
            pass

        async def update(self, body) -> PlatformSettingsResponse:
            assert body.require_signature_authorization is True
            return payload

    app.dependency_overrides[get_current_user] = lambda: fake_admin
    app.dependency_overrides[_build_admin_service] = lambda: _StubService()
    try:
        response = await client.patch(
            "/api/v1/admin/platform/settings",
            json={"require_signature_authorization": True},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 200
        assert response.json()["require_signature_authorization"] is True
    finally:
        app.dependency_overrides.clear()


async def test_service_get_returns_default_when_created() -> None:
    repo = AsyncMock()
    repo.get_or_create = AsyncMock(return_value=_settings())
    service = PlatformSettingsService(repo)
    result = await service.get()
    assert result.require_signature_authorization is False
    assert result.foro_fill_mode in (ForoFillMode.COMPANY, "company")
    assert result.id == PLATFORM_SETTINGS_ID


async def test_service_update_persists_flag() -> None:
    repo = AsyncMock()
    repo.update = AsyncMock(
        return_value=_settings(require_signature_authorization=True)
    )
    service = PlatformSettingsService(repo)
    from src.modules.platform_settings.schema import PlatformSettingsUpdate

    result = await service.update(
        PlatformSettingsUpdate(require_signature_authorization=True)
    )
    assert result.require_signature_authorization is True
    repo.update.assert_awaited_once()
    assert repo.update.await_args.args[0]["require_signature_authorization"] is True
