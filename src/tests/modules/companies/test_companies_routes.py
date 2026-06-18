"""Tests for the companies module routes."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.modules.companies.controller import CompaniesController
from src.modules.companies.routes import _build_controller
from src.modules.companies.schema import (
    CompanyAddressResponse,
    CompanyResponse,
    LogoPresignResponse,
)
from src.shared.dependencies.auth import CurrentUser, get_current_user
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit


def _sample_company(owner_id: UUID | None = None) -> CompanyResponse:
    now = utcnow()
    owner = owner_id or new_uuid()
    return CompanyResponse(
        id=new_uuid(),
        owner_user_id=owner,
        legal_name="Acme Indústria Ltda",
        trade_name="Acme",
        tax_id="12345678000190",
        email="contato@acme.com",
        phone="+55 11 99999-0000",
        address=CompanyAddressResponse(
            postal_code="01310-100",
            street="Av. Paulista",
            number="1000",
            complement="Sala 10",
            neighborhood="Bela Vista",
            city="São Paulo",
            state="SP",
        ),
        country="BR",
        website="https://acme.com",
        description="Empresa de reciclagem.",
        logo_storage_key="econmesh/logos/logo.png",
        logo_url="https://example.com/logo.png",
        sector="Reciclagem",
        is_active=True,
        created_at=now,
        updated_at=now,
    )


async def test_list_companies_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/companies")
    assert response.status_code == 401


async def test_list_companies_returns_user_companies(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123", email="alice@example.com")
    company = _sample_company()

    class _StubController(CompaniesController):
        def __init__(self) -> None:
            pass

        async def list(
            self, current_user: CurrentUser, page: int, page_size: int
        ) -> list[CompanyResponse]:
            assert current_user.uid == "firebase-uid-123"
            assert page == 1
            assert page_size == 20
            return [company]

    async def _override_user() -> CurrentUser:
        return fake_user

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.get(
            "/api/v1/companies",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["legal_name"] == "Acme Indústria Ltda"
        assert body[0]["tax_id"] == "12345678000190"
    finally:
        app.dependency_overrides.clear()


async def test_create_company_returns_201(app: FastAPI, client: AsyncClient) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123")
    company = _sample_company()

    class _StubController(CompaniesController):
        def __init__(self) -> None:
            pass

        async def create(
            self, payload, current_user: CurrentUser
        ) -> CompanyResponse:
            assert current_user.uid == "firebase-uid-123"
            assert payload.legal_name == "Nova Empresa Ltda"
            return company

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.post(
            "/api/v1/companies",
            headers={"Authorization": "Bearer fake-token"},
            json={
                "legal_name": "Nova Empresa Ltda",
                "tax_id": "12345678000190",
                "country": "BR",
            },
        )
        assert response.status_code == 201
        assert response.json()["legal_name"] == "Acme Indústria Ltda"
    finally:
        app.dependency_overrides.clear()


async def test_delete_company_returns_204(app: FastAPI, client: AsyncClient) -> None:
    company_id = new_uuid()
    fake_user = CurrentUser(uid="firebase-uid-123")

    class _StubController(CompaniesController):
        def __init__(self) -> None:
            pass

        async def delete(self, company_id_arg: UUID, current_user: CurrentUser) -> None:
            assert company_id_arg == company_id
            assert current_user.uid == "firebase-uid-123"

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.delete(
            f"/api/v1/companies/{company_id}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 204
    finally:
        app.dependency_overrides.clear()


async def test_presign_logo_returns_upload_url(app: FastAPI, client: AsyncClient) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123")
    now = utcnow()

    class _StubController(CompaniesController):
        def __init__(self) -> None:
            pass

        async def presign_logo(self, payload, current_user: CurrentUser) -> LogoPresignResponse:
            assert payload.filename == "logo.png"
            return LogoPresignResponse(
                upload_url="https://storage.example/upload",
                storage_key="econmesh/logos/test/logo.png",
                public_url="https://storage.example/logo.png",
                expires_at=now,
            )

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.post(
            "/api/v1/companies/logo/presign",
            headers={"Authorization": "Bearer fake-token"},
            json={"filename": "logo.png", "content_type": "image/png"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["storage_key"] == "econmesh/logos/test/logo.png"
        assert "upload_url" in body
    finally:
        app.dependency_overrides.clear()
