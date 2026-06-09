"""Tests for the registration / account-confirmation flow.

Service-level tests mock the repositories and Firebase so they need no real
Mongo/Redis. Route-level tests cover request validation and RBAC gating.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from src.core.config import Environment, Settings, get_settings
from src.core.exceptions import ConflictError, ForbiddenError
from src.modules.auth.model import EmailVerificationDocument, UserDocument
from src.modules.auth.schema import AdminRegisterRequest, RegisterRequest
from src.modules.auth.service import AuthService
from src.shared.constants.roles import DEFAULT_ROLE, Role
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit


def _firebase_mock() -> AsyncMock:
    fb = AsyncMock()
    fb.create_user = AsyncMock(return_value=SimpleNamespace(uid="fb-uid-1"))
    return fb


def _build_service() -> tuple[AuthService, AsyncMock, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    verifications = AsyncMock()
    redis_client = AsyncMock()
    fb = _firebase_mock()
    email = AsyncMock()
    service = AuthService(
        repository=repo,
        redis_client=redis_client,
        verification_repository=verifications,
        firebase_client=fb,
        email_client=email,
        settings=get_settings(),
    )
    # The email mock is reachable via ``service._email`` in individual tests.
    return service, repo, verifications, fb


# --------------------------------------------------------------- schema rules
def test_register_request_rejects_password_mismatch() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            full_name="Alice Doe",
            email="alice@example.com",
            password="supersecret",
            password_confirm="different",
        )


def test_register_request_accepts_matching_confirmation() -> None:
    payload = RegisterRequest(
        full_name="Alice Doe",
        email="alice@example.com",
        password="supersecret",
        password_confirm="supersecret",
    )
    assert payload.full_name == "Alice Doe"


# ------------------------------------------------------------------ register
async def test_register_creates_pending_user_and_issues_token() -> None:
    service, repo, verifications, fb = _build_service()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)

    payload = RegisterRequest(
        full_name="Alice Doe",
        email="alice@example.com",
        phone="+5511999999999",
        password="supersecret",
    )
    result = await service.register(payload)

    assert result.user.is_verified is False
    assert result.user.role == DEFAULT_ROLE
    assert result.verification_token is not None  # exposed in dev/test only
    fb.create_user.assert_awaited_once()
    fb.set_custom_user_claims.assert_awaited_once_with("fb-uid-1", {"role": DEFAULT_ROLE.value})
    verifications.create.assert_awaited_once()
    # The confirmation email must be dispatched with a link carrying the token.
    service._email.send_account_verification.assert_awaited_once()
    sent_kwargs = service._email.send_account_verification.await_args.kwargs
    assert sent_kwargs["to"] == "alice@example.com"
    assert "token=" in sent_kwargs["verify_url"]


async def test_register_does_not_expose_token_in_production() -> None:
    repo = AsyncMock()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(side_effect=lambda user: user)
    service = AuthService(
        repository=repo,
        redis_client=AsyncMock(),
        verification_repository=AsyncMock(),
        firebase_client=_firebase_mock(),
        email_client=AsyncMock(),
        settings=Settings(ENV=Environment.PRODUCTION),
    )

    payload = RegisterRequest(
        full_name="Alice Doe", email="alice@example.com", password="supersecret"
    )
    result = await service.register(payload)

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
    service, repo, _verifications, _fb = _build_service()
    repo.get_by_email = AsyncMock(
        return_value=UserDocument(firebase_uid="x", email="alice@example.com")
    )

    payload = RegisterRequest(
        full_name="Alice Doe", email="alice@example.com", password="supersecret"
    )
    with pytest.raises(ConflictError):
        await service.register(payload)


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


async def test_register_route_rejects_password_mismatch(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Dave Doe",
            "email": "dave@example.com",
            "password": "supersecret",
            "password_confirm": "nope",
        },
    )
    assert response.status_code == 422
    # Guard against the dependency-injection regression where ``db``/``redis_client``
    # were mis-detected as query params: the only validation error must be the
    # password mismatch, not a missing injected dependency.
    error_locs = [err.get("loc", []) for err in response.json()["details"]["errors"]]
    flat = {part for loc in error_locs for part in loc}
    assert "db" not in flat
    assert "redis_client" not in flat
