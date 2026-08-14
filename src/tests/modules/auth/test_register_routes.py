"""Tests for the registration / account-confirmation flow.

Service-level tests mock the repositories and Firebase so they need no real
Mongo/Redis. Route-level tests cover request validation and RBAC gating.
"""

from __future__ import annotations

import json
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, UploadFile
from httpx import AsyncClient
from pydantic import ValidationError
from starlette.datastructures import Headers

from src.core.config import Environment, Settings, get_settings
from src.core.exceptions import ConflictError, ForbiddenError, ValidationAppError
from src.modules.auth.model import EmailVerificationDocument, UserDocument
from src.modules.auth.schema import AdminRegisterRequest, RegisterCompanyInput, RegisterRequest
from src.modules.auth.service import AuthService
from src.modules.companies.model import CompanyDocument
from src.shared.constants.roles import DEFAULT_ROLE, Role
from src.shared.utils.compliance_upload import MAX_COMPLIANCE_BYTES
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit

_ADDRESS = {
    "postal_code": "01310100",
    "street": "Av. Paulista",
    "number": "1000",
    "city": "São Paulo",
    "state": "SP",
}

_COMPANY = RegisterCompanyInput(
    legal_name="Acme Indústria Ltda",
    trade_name="Acme",
    tax_id="11222333000181",
    email="contato@acme.com",
    phone="11999990000",
    address=_ADDRESS,
)


def _company_dict(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "legal_name": "Acme Indústria Ltda",
        "trade_name": "Acme",
        "tax_id": "11222333000181",
        "email": "contato@acme.com",
        "phone": "11999990000",
        "address": dict(_ADDRESS),
    }
    data.update(overrides)
    return data


def _register_payload(**overrides: object) -> RegisterRequest:
    data: dict[str, object] = {
        "full_name": "Alice Doe",
        "email": "alice@example.com",
        "password": "supersecret",
        "company": _COMPANY,
    }
    data.update(overrides)
    return RegisterRequest.model_validate(data)


def _pdf_upload(name: str = "doc.pdf", data: bytes = b"%PDF-1.4 test") -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(data),
        headers=Headers({"content-type": "application/pdf"}),
    )


async def _register_account(
    service: AuthService,
    payload: RegisterRequest | None = None,
    *,
    operating_license: UploadFile | None = None,
    mtr: UploadFile | None = None,
):
    return await service.register(
        payload or _register_payload(),
        operating_license=operating_license or _pdf_upload("lo.pdf"),
        mtr=mtr or _pdf_upload("mtr.pdf"),
    )


def _multipart(
    payload: dict[str, object],
    *,
    include_license: bool = True,
    include_mtr: bool = True,
    license_bytes: bytes = b"%PDF-1.4 test",
    mtr_bytes: bytes = b"%PDF-1.4 test",
    license_name: str = "lo.pdf",
    mtr_name: str = "mtr.pdf",
    license_type: str = "application/pdf",
    mtr_type: str = "application/pdf",
) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
    data = {"payload": json.dumps(payload)}
    files: dict[str, tuple[str, bytes, str]] = {}
    if include_license:
        files["operating_license"] = (license_name, license_bytes, license_type)
    if include_mtr:
        files["mtr"] = (mtr_name, mtr_bytes, mtr_type)
    return data, files


def _firebase_mock() -> AsyncMock:
    fb = AsyncMock()
    fb.create_user = AsyncMock(return_value=SimpleNamespace(uid="fb-uid-1"))
    fb.upload_storage_bytes = AsyncMock(return_value="https://storage.example/doc")
    fb.delete_user = AsyncMock()
    return fb


def _build_service() -> tuple[AuthService, AsyncMock, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    verifications = AsyncMock()
    redis_client = AsyncMock()
    fb = _firebase_mock()
    email = AsyncMock()
    companies = AsyncMock()
    companies.get_by_tax_id = AsyncMock(return_value=None)
    companies.create = AsyncMock(side_effect=lambda doc: doc)
    companies.delete = AsyncMock()
    companies.hard_delete = AsyncMock()
    users = AsyncMock()
    users.upsert_for_user = AsyncMock()
    service = AuthService(
        repository=repo,
        redis_client=redis_client,
        verification_repository=verifications,
        firebase_client=fb,
        email_client=email,
        settings=get_settings(),
        companies_repository=companies,
        users_repository=users,
    )
    return service, repo, verifications, fb


# --------------------------------------------------------------- schema rules
def test_register_request_rejects_password_mismatch() -> None:
    with pytest.raises(ValidationError):
        _register_payload(password_confirm="different")


def test_register_request_accepts_matching_confirmation() -> None:
    payload = _register_payload(password_confirm="supersecret")
    assert payload.full_name == "Alice Doe"
    assert payload.company.tax_id == "11222333000181"


def test_register_request_requires_company() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            full_name="Alice Doe",
            email="alice@example.com",
            password="supersecret",
        )


def test_register_company_normalizes_tax_id_digits() -> None:
    payload = _register_payload(
        company=_company_dict(legal_name="Acme Ltda", tax_id="11.222.333/0001-81")
    )
    assert payload.company.tax_id == "11222333000181"


def test_register_company_requires_email_phone_and_address() -> None:
    with pytest.raises(ValidationError):
        RegisterCompanyInput(
            legal_name="Acme Ltda",
            tax_id="11222333000181",
        )
    with pytest.raises(ValidationError):
        RegisterCompanyInput(
            legal_name="Acme Ltda",
            tax_id="11222333000181",
            email="contato@acme.com",
            phone="11999990000",
            address={"street": "Av. Paulista"},
        )


# ------------------------------------------------------------------ register
async def test_register_creates_pending_user_and_issues_token() -> None:
    service, repo, verifications, fb = _build_service()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)

    payload = _register_payload(phone="+5511999999999")
    result = await _register_account(service, payload)

    assert result.user.is_verified is False
    assert result.user.role == DEFAULT_ROLE
    assert result.verification_token is not None  # exposed in dev/test only
    fb.create_user.assert_awaited_once()
    fb.set_custom_user_claims.assert_awaited_once_with("fb-uid-1", {"role": DEFAULT_ROLE.value})
    fb.upload_storage_bytes.assert_awaited()
    assert fb.upload_storage_bytes.await_count == 2
    verifications.create.assert_awaited_once()
    service._companies.create.assert_awaited_once()
    created_company = service._companies.create.await_args.args[0]
    assert created_company.legal_name == "Acme Indústria Ltda"
    assert created_company.tax_id == "11222333000181"
    assert created_company.legal_representative == "Alice Doe"
    assert created_company.owner_user_id == result.user.id
    assert created_company.email == "contato@acme.com"
    assert created_company.phone == "11999990000"
    assert created_company.address is not None
    assert created_company.address.city == "São Paulo"
    assert created_company.address.postal_code == "01310100"
    assert created_company.operating_license is not None
    assert created_company.operating_license.storage_key
    assert created_company.operating_license.status == "pending"
    assert created_company.mtr_document is not None
    assert created_company.mtr_document.storage_key
    assert created_company.mtr_document.status == "pending"
    service._users.upsert_for_user.assert_awaited_once()
    # The confirmation email must be dispatched with a link carrying the token.
    service._email.send_account_verification.assert_awaited_once()
    sent_kwargs = service._email.send_account_verification.await_args.kwargs
    assert sent_kwargs["to"] == "alice@example.com"
    assert "token=" in sent_kwargs["verify_url"]


async def test_register_enqueues_document_review() -> None:
    service, repo, _verifications, _fb = _build_service()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)
    review = AsyncMock()
    service._compliance_review = review

    await _register_account(service)

    review.enqueue.assert_awaited_once()
    queued = review.enqueue.await_args.args[0]
    assert queued.legal_name == "Acme Indústria Ltda"
    assert queued.operating_license is not None
    assert queued.mtr_document is not None


async def test_register_does_not_expose_token_in_production() -> None:
    repo = AsyncMock()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)
    companies = AsyncMock()
    companies.get_by_tax_id = AsyncMock(return_value=None)
    companies.create = AsyncMock(side_effect=lambda doc: doc)
    users = AsyncMock()
    users.upsert_for_user = AsyncMock()
    service = AuthService(
        repository=repo,
        redis_client=AsyncMock(),
        verification_repository=AsyncMock(),
        firebase_client=_firebase_mock(),
        email_client=AsyncMock(),
        settings=Settings(ENV=Environment.PRODUCTION),
        companies_repository=companies,
        users_repository=users,
    )

    payload = _register_payload()
    result = await _register_account(service, payload)

    assert result.verification_token is None  # token only delivered via email
    service._email.send_account_verification.assert_awaited_once()


async def test_resend_is_throttled_by_cooldown() -> None:
    service, repo, verifications, _fb = _build_service()
    repo.get_by_email = AsyncMock(
        return_value=UserDocument(firebase_uid="fb-uid-1", email="a@b.com", is_verified=False)
    )
    # Redis SET NX returns falsy when the cooldown key already exists.
    service._redis.set = AsyncMock(return_value=None)

    result = await service.resend_verification("a@b.com")

    assert "exists" in result.message.lower()
    verifications.create.assert_not_awaited()
    service._email.send_account_verification.assert_not_awaited()


async def test_register_rejects_duplicate_email() -> None:
    service, repo, _verifications, fb = _build_service()
    repo.get_by_email = AsyncMock(
        return_value=UserDocument(firebase_uid="x", email="alice@example.com")
    )

    payload = _register_payload()
    with pytest.raises(ConflictError):
        await _register_account(service, payload)
    fb.create_user.assert_not_awaited()


async def test_register_rejects_duplicate_tax_id_without_creating_firebase() -> None:
    service, repo, _verifications, fb = _build_service()
    repo.get_by_email = AsyncMock(return_value=None)
    service._companies.get_by_tax_id = AsyncMock(
        return_value=CompanyDocument(
            owner_user_id=new_uuid(),
            legal_name="Existing Ltda",
            tax_id="11222333000181",
            is_active=True,
        )
    )

    with pytest.raises(ConflictError) as exc:
        await _register_account(service)
    assert exc.value.code == "tax_id_exists"
    fb.create_user.assert_not_awaited()
    repo.create_user.assert_not_awaited()


async def test_admin_register_auto_confirms_and_skips_token() -> None:
    service, repo, verifications, _fb = _build_service()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)

    payload = AdminRegisterRequest(
        full_name="Bob Admin",
        email="bob@example.com",
        password="supersecret",
        role=Role.ADMIN,
        auto_confirm=True,
    )
    result = await service.register_by_admin(payload)

    assert result.user.is_verified is True
    assert result.user.role == Role.ADMIN
    assert result.verification_token is None
    verifications.create.assert_not_awaited()


# ---------------------------------------------------------------- verification
async def test_verify_account_confirms_user() -> None:
    service, repo, verifications, fb = _build_service()
    user_id = new_uuid()
    record = EmailVerificationDocument(
        user_id=user_id,
        firebase_uid="fb-uid-1",
        email="alice@example.com",
        token_hash="hash",
        expires_at=utcnow() + timedelta(hours=1),
    )
    verifications.get_by_token_hash = AsyncMock(return_value=record)
    verifications.consume = AsyncMock(return_value=True)

    result = await service.verify_account("raw-token-value-1234")

    assert "confirmed" in result.message.lower()
    repo.mark_verified.assert_awaited_once_with(user_id)
    fb.update_user.assert_awaited_once_with("fb-uid-1", email_verified=True)


async def test_verify_account_is_idempotent_after_success() -> None:
    service, repo, verifications, fb = _build_service()
    user_id = new_uuid()
    consumed_at = utcnow()
    record = EmailVerificationDocument(
        user_id=user_id,
        firebase_uid="fb-uid-1",
        email="alice@example.com",
        token_hash="hash",
        expires_at=utcnow() + timedelta(hours=1),
        consumed_at=consumed_at,
    )
    verifications.get_by_token_hash = AsyncMock(return_value=record)
    repo.get_by_id = AsyncMock(
        return_value=UserDocument(
            id=user_id,
            firebase_uid="fb-uid-1",
            email="alice@example.com",
            is_verified=True,
        )
    )

    result = await service.verify_account("raw-token-value-1234")

    assert "confirmed" in result.message.lower()
    repo.mark_verified.assert_not_awaited()
    fb.update_user.assert_not_awaited()


async def test_verify_account_rejects_expired_token() -> None:
    service, _repo, verifications, _fb = _build_service()
    record = EmailVerificationDocument(
        user_id=new_uuid(),
        firebase_uid="fb-uid-1",
        email="alice@example.com",
        token_hash="hash",
        expires_at=utcnow() - timedelta(minutes=1),
    )
    verifications.get_by_token_hash = AsyncMock(return_value=record)

    from src.core.exceptions import AuthError

    with pytest.raises(AuthError):
        await service.verify_account("raw-token-value-1234")


# ---------------------------------------------------------------- login gate
async def test_login_blocked_until_account_is_verified() -> None:
    service, repo, _verifications, fb = _build_service()
    fb.verify_id_token = AsyncMock(return_value={"uid": "fb-uid-1", "email": "a@b.com"})
    service._redis.delete = AsyncMock()
    repo.upsert_from_firebase = AsyncMock(
        return_value=UserDocument(
            firebase_uid="fb-uid-1", email="a@b.com", is_verified=False, is_active=True
        )
    )

    with pytest.raises(ForbiddenError) as exc:
        await service.login_with_id_token("a" * 20)
    assert exc.value.code == "account_not_verified"


async def test_login_succeeds_for_verified_user() -> None:
    service, repo, _verifications, fb = _build_service()
    fb.verify_id_token = AsyncMock(return_value={"uid": "fb-uid-1", "email": "a@b.com"})
    service._redis.delete = AsyncMock()
    repo.upsert_from_firebase = AsyncMock(
        return_value=UserDocument(
            firebase_uid="fb-uid-1", email="a@b.com", is_verified=True, is_active=True
        )
    )

    result = await service.login_with_id_token("a" * 20)
    assert result.user.firebase_uid == "fb-uid-1"
    assert result.user.is_verified is True
    service._redis.delete.assert_awaited_once_with("auth:revoked:fb-uid-1")


async def test_admin_login_rejects_non_admin_role() -> None:
    service, repo, _verifications, fb = _build_service()
    fb.verify_id_token = AsyncMock(return_value={"uid": "fb-uid-1", "email": "a@b.com", "role": "viewer"})
    service._redis.delete = AsyncMock()
    service._redis.set = AsyncMock()
    repo.upsert_from_firebase = AsyncMock(
        return_value=UserDocument(
            firebase_uid="fb-uid-1",
            email="a@b.com",
            is_verified=True,
            is_active=True,
            role=Role.VIEWER,
        )
    )

    with pytest.raises(ForbiddenError) as exc:
        await service.admin_login_with_id_token("a" * 20)
    assert exc.value.code == "admin_required"


async def test_admin_login_succeeds_for_admin_role() -> None:
    service, repo, _verifications, fb = _build_service()
    fb.verify_id_token = AsyncMock(
        return_value={"uid": "fb-uid-1", "email": "admin@b.com", "role": "admin"}
    )
    service._redis.delete = AsyncMock()
    service._redis.set = AsyncMock()
    repo.upsert_from_firebase = AsyncMock(
        return_value=UserDocument(
            firebase_uid="fb-uid-1",
            email="admin@b.com",
            is_verified=True,
            is_active=True,
            role=Role.ADMIN,
        )
    )

    result = await service.admin_login_with_id_token("a" * 20)
    assert result.user.role == Role.ADMIN


# ------------------------------------------------------------------- routes
async def test_admin_create_user_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/admin/users",
        json={
            "full_name": "Carol Admin",
            "email": "carol@example.com",
            "password": "supersecret",
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == "missing_token"


async def test_admin_create_user_rejects_non_admin(
    app: FastAPI, client: AsyncClient
) -> None:
    from src.shared.constants.roles import Role
    from src.shared.dependencies.auth import CurrentUser, get_current_user

    async def _override() -> CurrentUser:
        return CurrentUser(
            uid="firebase-uid-viewer",
            email="viewer@example.com",
            role=Role.VIEWER,
            email_verified=True,
        )

    app.dependency_overrides[get_current_user] = _override
    try:
        response = await client.post(
            "/api/v1/auth/admin/users",
            json={
                "full_name": "Carol Admin",
                "email": "carol@example.com",
                "password": "supersecret",
            },
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "role_required"
    finally:
        app.dependency_overrides.clear()


async def test_admin_login_route_rejects_non_admin(
    app: FastAPI, client: AsyncClient
) -> None:
    from src.modules.auth.controller import AuthController
    from src.modules.auth.routes import _build_controller
    from src.core.exceptions import ForbiddenError

    class _StubController(AuthController):
        def __init__(self) -> None:
            pass

        async def admin_login(self, payload):  # type: ignore[override]
            raise ForbiddenError("Admin access required.", code="admin_required")

    app.dependency_overrides[_build_controller] = lambda: _StubController()
    try:
        response = await client.post(
            "/api/v1/auth/admin/login",
            json={"id_token": "a" * 20},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "admin_required"
    finally:
        app.dependency_overrides.clear()


async def test_register_route_rejects_password_mismatch(client: AsyncClient) -> None:
    data, files = _multipart(
        {
            "full_name": "Dave Doe",
            "email": "dave@example.com",
            "password": "supersecret",
            "password_confirm": "nope",
            "company": _company_dict(),
        }
    )
    response = await client.post("/api/v1/auth/register", data=data, files=files)
    assert response.status_code == 422
    # Guard against the dependency-injection regression where ``db``/``redis_client``
    # were mis-detected as query params: the only validation error must be the
    # password mismatch, not a missing injected dependency.
    error_locs = [err.get("loc", []) for err in response.json()["details"]["errors"]]
    flat = {part for loc in error_locs for part in loc}
    assert "db" not in flat
    assert "redis_client" not in flat


async def test_register_route_rejects_missing_company(client: AsyncClient) -> None:
    data, files = _multipart(
        {
            "full_name": "Dave Doe",
            "email": "dave@example.com",
            "password": "supersecret",
        }
    )
    response = await client.post("/api/v1/auth/register", data=data, files=files)
    assert response.status_code == 422
    error_locs = [err.get("loc", []) for err in response.json()["details"]["errors"]]
    flat = {part for loc in error_locs for part in loc}
    assert "company" in flat


async def test_register_route_rejects_missing_company_contact_fields(client: AsyncClient) -> None:
    data, files = _multipart(
        {
            "full_name": "Dave Doe",
            "email": "dave@example.com",
            "password": "supersecret",
            "company": {
                "legal_name": "Acme Ltda",
                "tax_id": "11222333000181",
            },
        }
    )
    response = await client.post("/api/v1/auth/register", data=data, files=files)
    assert response.status_code == 422


async def test_register_route_rejects_missing_document_file(client: AsyncClient) -> None:
    data, files = _multipart(
        {
            "full_name": "Dave Doe",
            "email": "dave@example.com",
            "password": "supersecret",
            "company": _company_dict(),
        },
        include_mtr=False,
    )
    response = await client.post("/api/v1/auth/register", data=data, files=files)
    assert response.status_code == 422
    error_locs = [err.get("loc", []) for err in response.json()["details"]["errors"]]
    flat = {part for loc in error_locs for part in loc}
    assert "mtr" in flat


async def test_register_rejects_invalid_document_type() -> None:
    service, repo, _verifications, fb = _build_service()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)
    bad = UploadFile(
        filename="notes.txt",
        file=BytesIO(b"not a document"),
        headers=Headers({"content-type": "text/plain"}),
    )
    with pytest.raises(ValidationAppError) as exc:
        await _register_account(service, operating_license=bad)
    assert exc.value.code == "invalid_content_type"
    fb.delete_user.assert_awaited()


async def test_register_rejects_oversized_document() -> None:
    service, repo, _verifications, fb = _build_service()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)
    big = _pdf_upload("huge.pdf", data=b"x" * (MAX_COMPLIANCE_BYTES + 1))
    with pytest.raises(ValidationAppError) as exc:
        await _register_account(service, mtr=big)
    assert exc.value.code == "file_too_large"
    fb.delete_user.assert_awaited()
