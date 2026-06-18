"""Tests for the opportunities module routes."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.modules.opportunities.controller import OpportunitiesController
from src.modules.opportunities.model import (
    OfferDemand,
    OpportunityPeriodicity,
    OpportunityType,
)
from src.modules.opportunities.routes import _build_controller
from src.modules.opportunities.schema import (
    OpportunityImagePresignResponse,
    OpportunityImageResponse,
    OpportunityListResponse,
    OpportunityResponse,
)
from src.shared.dependencies.auth import CurrentUser, get_current_user
from src.shared.schemas.responses import StorageUploadResponse
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit


def _sample_opportunity(owner_id: UUID | None = None) -> OpportunityResponse:
    now = utcnow()
    owner = owner_id or new_uuid()
    company_id = new_uuid()
    return OpportunityResponse(
        id=new_uuid(),
        company_id=company_id,
        company_name="Acme Reciclagem",
        owner_user_id=owner,
        title="Venda de PET Triturado",
        description="PET triturado de alta qualidade para reciclagem industrial.",
        opportunity_type=OpportunityType.COMERCIALIZACAO,
        offer_demand=OfferDemand.GERADOR,
        category="Plástico",
        technical_detail="PET",
        purity_percent=95.0,
        physical_state="Triturado (Flakes)",
        periodicity=OpportunityPeriodicity.CONTINUA,
        quantity=10.0,
        unit="tonelada",
        price=3500.0,
        price_negotiable=False,
        city="São Paulo",
        state="SP",
        images=[
            OpportunityImageResponse(
                storage_key="econmesh/images/test.jpg",
                url="https://example.com/test.jpg",
                is_primary=True,
                sort_order=0,
            )
        ],
        created_at=now,
        updated_at=now,
    )


async def test_list_opportunities_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/opportunities")
    assert response.status_code == 401


async def test_list_opportunities_returns_envelope(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123", email="alice@example.com")
    opportunity = _sample_opportunity()

    class _StubController(OpportunitiesController):
        def __init__(self) -> None:
            pass

        async def list(self, params, current_user: CurrentUser) -> OpportunityListResponse:
            assert current_user.uid == "firebase-uid-123"
            assert params.page == 1
            assert params.page_size == 12
            return OpportunityListResponse(
                items=[opportunity],
                total=1,
                page=1,
                page_size=12,
                has_more=False,
            )

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.get(
            "/api/v1/opportunities",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["has_more"] is False
        assert len(body["items"]) == 1
        assert body["items"][0]["title"] == "Venda de PET Triturado"
    finally:
        app.dependency_overrides.clear()


async def test_create_opportunity_returns_201(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123")
    opportunity = _sample_opportunity()
    company_id = new_uuid()

    class _StubController(OpportunitiesController):
        def __init__(self) -> None:
            pass

        async def create(self, payload, current_user: CurrentUser) -> OpportunityResponse:
            assert current_user.uid == "firebase-uid-123"
            assert payload.title == "Nova Oportunidade"
            assert payload.company_id == company_id
            return opportunity

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.post(
            "/api/v1/opportunities",
            headers={"Authorization": "Bearer fake-token"},
            json={
                "company_id": str(company_id),
                "title": "Nova Oportunidade",
                "description": "Descrição detalhada da oportunidade de teste.",
                "opportunity_type": "comercializacao",
                "offer_demand": "gerador",
                "category": "Plástico",
                "technical_detail": "PET",
                "physical_state": "Triturado (Flakes)",
                "periodicity": "continua",
                "quantity": 5,
                "unit": "tonelada",
                "price": 1000,
                "price_negotiable": False,
                "city": "São Paulo",
                "state": "SP",
                "images": [],
            },
        )
        assert response.status_code == 201
        assert response.json()["title"] == "Venda de PET Triturado"
    finally:
        app.dependency_overrides.clear()


async def test_delete_opportunity_returns_204(
    app: FastAPI, client: AsyncClient
) -> None:
    opportunity_id = new_uuid()
    fake_user = CurrentUser(uid="firebase-uid-123")

    class _StubController(OpportunitiesController):
        def __init__(self) -> None:
            pass

        async def delete(
            self, opportunity_id_arg: UUID, current_user: CurrentUser
        ) -> None:
            assert opportunity_id_arg == opportunity_id
            assert current_user.uid == "firebase-uid-123"

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.delete(
            f"/api/v1/opportunities/{opportunity_id}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 204
    finally:
        app.dependency_overrides.clear()


async def test_presign_image_returns_upload_url(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123")
    now = utcnow()

    class _StubController(OpportunitiesController):
        def __init__(self) -> None:
            pass

        async def presign_image(
            self, payload, current_user: CurrentUser
        ) -> OpportunityImagePresignResponse:
            assert payload.filename == "photo.jpg"
            return OpportunityImagePresignResponse(
                upload_url="https://storage.example/upload",
                storage_key="econmesh/images/test/photo.jpg",
                public_url="https://storage.example/photo.jpg",
                expires_at=now,
            )

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.post(
            "/api/v1/opportunities/images/presign",
            headers={"Authorization": "Bearer fake-token"},
            json={"filename": "photo.jpg", "content_type": "image/jpeg"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["storage_key"] == "econmesh/images/test/photo.jpg"
        assert "upload_url" in body
    finally:
        app.dependency_overrides.clear()


async def test_upload_image_returns_storage_key(
    app: FastAPI, client: AsyncClient
) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123")

    class _StubController(OpportunitiesController):
        def __init__(self) -> None:
            pass

        async def upload_image(self, file, current_user: CurrentUser) -> StorageUploadResponse:
            assert current_user.uid == fake_user.uid
            assert file.filename == "photo.jpg"
            return StorageUploadResponse(
                storage_key="econmesh/images/test/photo.jpg",
                public_url="https://storage.example/photo.jpg",
            )

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.post(
            "/api/v1/opportunities/images/upload",
            headers={"Authorization": "Bearer fake-token"},
            files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["storage_key"] == "econmesh/images/test/photo.jpg"
        assert body["public_url"] == "https://storage.example/photo.jpg"
    finally:
        app.dependency_overrides.clear()
