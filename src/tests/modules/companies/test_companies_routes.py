"""Tests for the companies module routes."""

from __future__ import annotations

from uuid import UUID
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, UploadFile
from httpx import AsyncClient

from src.modules.companies.controller import CompaniesController
from src.modules.companies.routes import _build_controller
from src.modules.companies.schema import (
    CompanyAddressResponse,
    CompanyComplianceFileResponse,
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
        operating_license=CompanyComplianceFileResponse(
            storage_key="econmesh/company-docs/x/lo.pdf",
            public_url="https://example.com/lo.pdf",
            filename="lo.pdf",
            content_type="application/pdf",
        ),
        mtr_document=CompanyComplianceFileResponse(
            storage_key="econmesh/company-docs/x/mtr.pdf",
            public_url="https://example.com/mtr.pdf",
            filename="mtr.pdf",
            content_type="application/pdf",
        ),
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


async def test_create_rejects_when_owner_already_has_company() -> None:
    from src.core.exceptions import ConflictError
    from src.modules.auth.model import UserDocument
    from src.modules.companies.schema import CompanyCreate
    from src.modules.companies.service import CompaniesService

    repo = AsyncMock()
    repo.count_for_owner = AsyncMock(return_value=1)
    auth_repo = AsyncMock()
    auth_repo.get_by_firebase_uid = AsyncMock(
        return_value=UserDocument(firebase_uid="fb-uid-1", email="alice@example.com")
    )
    service = CompaniesService(repo, auth_repo)

    with pytest.raises(ConflictError) as exc:
        await service.create(
            CompanyCreate(legal_name="Nova Empresa Ltda", tax_id="11222333000181"),
            firebase_uid="fb-uid-1",
        )
    assert exc.value.code == "owner_already_has_company"
    repo.create.assert_not_awaited()


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


async def test_upload_document_returns_company(app: FastAPI, client: AsyncClient) -> None:
    fake_user = CurrentUser(uid="firebase-uid-123")
    company = _sample_company()
    company_id = company.id

    class _StubController(CompaniesController):
        def __init__(self) -> None:
            pass

        async def upload_document(
            self,
            company_id_arg: UUID,
            kind: str,
            file: UploadFile,
            current_user: CurrentUser,
        ) -> CompanyResponse:
            assert company_id_arg == company_id
            assert kind == "operating_license"
            assert current_user.uid == "firebase-uid-123"
            return company

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.post(
            f"/api/v1/companies/{company_id}/documents/operating_license/upload",
            headers={"Authorization": "Bearer fake-token"},
            files={"file": ("lo.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["operating_license"]["filename"] == "lo.pdf"
    finally:
        app.dependency_overrides.clear()


async def test_upload_document_enqueues_review_for_owner() -> None:
    from io import BytesIO
    from unittest.mock import patch

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from src.modules.auth.model import UserDocument
    from src.modules.companies.model import (
        CompanyComplianceFile,
        CompanyDocument,
        ComplianceDocumentStatus,
    )
    from src.modules.companies.service import CompaniesService

    owner = UserDocument(firebase_uid="fb-uid-1", email="alice@example.com")
    company = CompanyDocument(
        id=new_uuid(),
        owner_user_id=owner.id,
        legal_name="Acme Ltda",
        tax_id="11222333000181",
        is_active=True,
    )
    uploaded = CompanyComplianceFile(
        storage_key="econmesh/company-docs/x/lo.pdf",
        public_url="https://example.com/lo.pdf",
        filename="lo.pdf",
        content_type="application/pdf",
        status=ComplianceDocumentStatus.PENDING,
    )
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=company)
    repo.update = AsyncMock(return_value=company.model_copy(update={"operating_license": uploaded}))
    auth_repo = AsyncMock()
    auth_repo.get_by_firebase_uid = AsyncMock(return_value=owner)
    review = AsyncMock()
    service = CompaniesService(repo, auth_repo, compliance_review=review)
    file = UploadFile(
        filename="lo.pdf",
        file=BytesIO(b"%PDF-1.4"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with patch(
        "src.modules.companies.service.upload_compliance_file",
        AsyncMock(return_value=uploaded),
    ):
        await service.upload_document(
            company.id, "operating_license", file, firebase_uid="fb-uid-1"
        )
    review.enqueue.assert_awaited_once()


async def test_admin_upload_document_marks_approved() -> None:
    from io import BytesIO
    from unittest.mock import patch

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from src.modules.companies.model import (
        CompanyComplianceFile,
        CompanyDocument,
        ComplianceDocumentStatus,
    )
    from src.modules.companies.service import CompaniesService

    company = CompanyDocument(
        id=new_uuid(),
        owner_user_id=new_uuid(),
        legal_name="Acme Ltda",
        tax_id="11222333000181",
        is_active=True,
    )
    pending = CompanyComplianceFile(
        storage_key="econmesh/company-docs/x/lo.pdf",
        public_url="https://example.com/lo.pdf",
        filename="lo.pdf",
        content_type="application/pdf",
        status=ComplianceDocumentStatus.PENDING,
    )
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=company)

    async def _update(_id, patch):
        file = CompanyComplianceFile.model_validate(patch["operating_license"])
        return company.model_copy(update={"operating_license": file})

    repo.update = AsyncMock(side_effect=_update)
    review = AsyncMock()
    service = CompaniesService(repo, AsyncMock(), compliance_review=review)
    file = UploadFile(
        filename="lo.pdf",
        file=BytesIO(b"%PDF-1.4"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with patch(
        "src.modules.companies.service.upload_compliance_file",
        AsyncMock(return_value=pending),
    ):
        result = await service.upload_document(
            company.id, "operating_license", file, as_admin=True
        )
    assert result.operating_license is not None
    assert result.operating_license.status == "approved"
    review.enqueue.assert_not_awaited()
