"""Business rules for authentication / identity sync."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from src.core.config import Environment, Settings, get_settings
from src.core.exceptions import AuthError, ConflictError, ForbiddenError, NotFoundError
from src.core.firebase import FirebaseAdmin, firebase
from src.core.logging import get_logger
from src.infrastructure.email import EmailSender, email_sender
from src.modules.auth.model import EmailVerificationDocument, UserDocument
from src.modules.auth.repository import AuthRepository, EmailVerificationRepository
from src.modules.auth.schema import (
    AdminRegisterRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    TokenIntrospectionResponse,
)
from src.shared.constants.roles import DEFAULT_ROLE, Role
from src.shared.schemas.responses import MessageResponse
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

_SESSION_KEY_PREFIX = "auth:session:"
_REVOCATION_KEY_PREFIX = "auth:revoked:"
_RESEND_COOLDOWN_KEY_PREFIX = "auth:verify:cooldown:"

# How long a confirmation link stays valid.
_VERIFICATION_TTL = timedelta(hours=24)
# Minimum gap between confirmation emails for the same account (anti-abuse).
_RESEND_COOLDOWN_SECONDS = 60


class AuthService:
    """Orchestrates Firebase verification, user sync, and session caching."""

    def __init__(
        self,
        *,
        repository: AuthRepository,
        redis_client: Redis,
        verification_repository: EmailVerificationRepository | None = None,
        firebase_client: FirebaseAdmin | None = None,
        email_client: EmailSender | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._repo = repository
        self._verifications = verification_repository
        self._redis = redis_client
        self._firebase = firebase_client or firebase
        self._email = email_client or email_sender
        self._settings = settings or get_settings()

    # ------------------------------------------------------------- register
    async def register(self, payload: RegisterRequest) -> RegisterResponse:
        """Self-service signup for a standard (non-privileged) user."""
        return await self._create_account(
            payload,
            role=DEFAULT_ROLE,
            auto_confirm=False,
        )

    async def register_by_admin(self, payload: AdminRegisterRequest) -> RegisterResponse:
        """Privileged creation. Caller MUST already be authorised as an admin."""
        return await self._create_account(
            payload,
            role=payload.role,
            auto_confirm=payload.auto_confirm,
        )

    async def _create_account(
        self,
        payload: RegisterRequest,
        *,
        role: Role,
        auto_confirm: bool,
    ) -> RegisterResponse:
        # ``APIModel`` serialises enums to their values, so normalise back.
        role = Role(role)

        # Guard against duplicates early for a clean 409 (Firebase also enforces).
        if await self._repo.get_by_email(payload.email) is not None:
            raise ConflictError(
                "An account with this email already exists.",
                code="email_already_exists",
            )

        fb_user = await self._firebase.create_user(
            email=payload.email,
            password=payload.password,
            display_name=payload.full_name,
            email_verified=auto_confirm,
            disabled=False,
        )
        firebase_uid = str(fb_user.uid)

        # From here on, roll back the Firebase identity if local persistence fails.
        try:
            await self._firebase.set_custom_user_claims(firebase_uid, {"role": role.value})

            now = utcnow()
            user = UserDocument(
                firebase_uid=firebase_uid,
                email=payload.email,
                name=payload.full_name,
                phone=payload.phone,
                email_verified=auto_confirm,
                is_verified=auto_confirm,
                role=role,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            await self._repo.create_user(user)
        except Exception:
            logger.exception("register_persist_failed_rolling_back", firebase_uid=firebase_uid)
            await self._firebase.delete_user(firebase_uid)
            raise

        raw_token: str | None = None
        if not auto_confirm:
            raw_token = await self._issue_verification_token(user)
            await self._send_verification_email(user, raw_token)
            logger.info(
                "account_registered_pending_confirmation",
                user_id=str(user.id),
                email=payload.email,
            )
        else:
            logger.info("account_created_confirmed", user_id=str(user.id), role=role.value)

        message = (
            "Account created. Check your email to confirm before signing in."
            if not auto_confirm
            else "Account created and confirmed."
        )
        return RegisterResponse(
            user=self._to_me(user),
            message=message,
            verification_token=self._expose_token(raw_token),
        )

    # --------------------------------------------------------- verification
    async def verify_account(self, raw_token: str) -> MessageResponse:
        """Confirm an account from its emailed token (single-use, time-boxed)."""
        repo = self._require_verifications()
        token_hash = self._hash_token(raw_token)

        record = await repo.get_by_token_hash(token_hash)
        if record is None:
            raise AuthError("Invalid confirmation token.", code="invalid_verification_token")
        if record.consumed_at is not None:
            raise AuthError("Confirmation token already used.", code="verification_token_used")
        if record.expires_at <= utcnow():
            raise AuthError("Confirmation token expired.", code="verification_token_expired")

        # Atomically claim the token so a replay cannot double-confirm.
        if not await repo.consume(record.id):
            raise AuthError("Confirmation token already used.", code="verification_token_used")

        await self._repo.mark_verified(record.user_id)
        await self._firebase.update_user(record.firebase_uid, email_verified=True)
        await repo.delete_for_user(record.user_id)

        logger.info("account_confirmed", user_id=str(record.user_id))
        return MessageResponse(message="Account confirmed. You can now sign in.")

    async def resend_verification(self, email: str) -> MessageResponse:
        """Re-issue a confirmation token for an unconfirmed account."""
        repo = self._require_verifications()
        user = await self._repo.get_by_email(email)

        # Always return the same response to avoid leaking which emails exist.
        generic = MessageResponse(
            message="If the account exists and is unconfirmed, a new email was sent."
        )
        if user is None or user.is_verified:
            return generic

        # Throttle per account to prevent email-bombing a victim's inbox.
        if not await self._claim_resend_slot(email):
            logger.info("verification_resend_throttled", user_id=str(user.id))
            return generic

        await repo.delete_for_user(user.id)
        raw_token = await self._issue_verification_token(user)
        await self._send_verification_email(user, raw_token)
        logger.info("verification_resent", user_id=str(user.id))

        exposed = self._expose_token(raw_token)
        if exposed is not None:
            return MessageResponse(message=generic.message, data={"verification_token": exposed})
        return generic

    # ---------------------------------------------------------------- login
    async def login_with_id_token(self, id_token: str) -> LoginResponse:
        """Verify a Firebase ID token, upsert the user, cache the session."""
        claims = await self._firebase.verify_id_token(id_token)
        firebase_uid = str(claims["uid"])
        # A freshly verified Firebase token is a new sign-in — clear any stale
        # local logout marker so the user is not locked out after signing out.
        await self._redis.delete(self._revocation_key(firebase_uid))

        user = await self._repo.upsert_from_firebase(claims)
        self._guard_can_login(user)
        await self._cache_session(user, claims)

        logger.info("auth_login_success", firebase_uid=user.firebase_uid, user_id=str(user.id))

        return LoginResponse(
            user=self._to_me(user),
            token=self._to_token_introspection(claims),
        )

    # ----------------------------------------------------------------- me
    async def get_me(self, firebase_uid: str) -> MeResponse:
        user = await self._repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return self._to_me(user)

    # ---------------------------------------------------------------- logout
    async def logout(self, firebase_uid: str) -> None:
        """Drop the cached identity for the current session."""
        await self._redis.delete(self._session_key(firebase_uid))
        logger.info("auth_logout", firebase_uid=firebase_uid)

    async def revoke_all_sessions(self, firebase_uid: str) -> None:
        """Revoke Firebase refresh tokens AND local sessions (logout-everywhere)."""
        await self._firebase.revoke_refresh_tokens(firebase_uid)
        await self._redis.delete(self._session_key(firebase_uid))
        await self._redis.set(
            self._revocation_key(firebase_uid),
            "1",
            ex=self._settings.SESSION_TTL_SECONDS,
        )
        logger.warning("auth_revoke_all", firebase_uid=firebase_uid)

    # ---------------------------------------------------------------- helpers
    async def _issue_verification_token(self, user: UserDocument) -> str:
        repo = self._require_verifications()
        raw_token = secrets.token_urlsafe(32)
        record = EmailVerificationDocument(
            user_id=user.id,
            firebase_uid=user.firebase_uid,
            email=user.email or "",
            token_hash=self._hash_token(raw_token),
            expires_at=utcnow() + _VERIFICATION_TTL,
        )
        await repo.create(record)
        return raw_token

    async def _send_verification_email(self, user: UserDocument, raw_token: str) -> None:
        """Email the confirmation link. Never blocks account creation on failure."""
        if not user.email:
            return
        verify_url = self._build_verify_url(raw_token)
        try:
            await self._email.send_account_verification(to=user.email, verify_url=verify_url)
        except Exception:  # noqa: BLE001 — registration already succeeded; user can resend
            logger.exception("verification_email_failed", user_id=str(user.id))

    def _build_verify_url(self, raw_token: str) -> str:
        base = self._settings.FRONTEND_VERIFY_URL
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{urlencode({'token': raw_token})}"

    async def _claim_resend_slot(self, email: str) -> bool:
        """Return True if a resend is allowed now; sets a short cooldown if so."""
        key = f"{_RESEND_COOLDOWN_KEY_PREFIX}{self._hash_token(email.lower())}"
        was_set = await self._redis.set(key, "1", nx=True, ex=_RESEND_COOLDOWN_SECONDS)
        return bool(was_set)

    def _expose_token(self, raw_token: str | None) -> str | None:
        """Return the raw token only in non-deployed envs (dev/test).

        Production and staging NEVER receive the token in an API response — it is
        delivered exclusively via email.
        """
        if raw_token is None:
            return None
        if self._settings.ENV in {Environment.DEVELOPMENT, Environment.TEST}:
            return raw_token
        return None

    def _require_verifications(self) -> EmailVerificationRepository:
        if self._verifications is None:
            raise RuntimeError("EmailVerificationRepository is not configured.")
        return self._verifications

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _guard_can_login(user: UserDocument) -> None:
        if not user.is_active:
            raise ForbiddenError("This account is disabled.", code="account_disabled")
        if not user.is_verified:
            raise ForbiddenError(
                "Confirm your account before signing in.",
                code="account_not_verified",
            )

    async def _cache_session(self, user: UserDocument, claims: dict[str, Any]) -> None:
        payload = {
            "uid": user.firebase_uid,
            "user_id": str(user.id),
            "role": str(user.role),
            "email": user.email or "",
            "iat": claims.get("iat"),
            "exp": claims.get("exp"),
        }
        await self._redis.hset(self._session_key(user.firebase_uid), mapping=payload)  # type: ignore[arg-type]
        await self._redis.expire(
            self._session_key(user.firebase_uid), self._settings.SESSION_TTL_SECONDS
        )

    @staticmethod
    def _session_key(firebase_uid: str) -> str:
        return f"{_SESSION_KEY_PREFIX}{firebase_uid}"

    @staticmethod
    def _revocation_key(firebase_uid: str) -> str:
        return f"{_REVOCATION_KEY_PREFIX}{firebase_uid}"

    @staticmethod
    def _to_me(user: UserDocument) -> MeResponse:
        return MeResponse(
            id=user.id,
            firebase_uid=user.firebase_uid,
            email=user.email,
            name=user.name,
            phone=user.phone,
            picture=user.picture,
            email_verified=user.email_verified,
            is_verified=user.is_verified,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )

    @staticmethod
    def _to_token_introspection(claims: dict[str, Any]) -> TokenIntrospectionResponse:
        return TokenIntrospectionResponse(
            uid=str(claims["uid"]),
            issuer=claims.get("iss"),
            audience=claims.get("aud"),
            expires_at=claims.get("exp"),
            issued_at=claims.get("iat"),
            email_verified=bool(claims.get("email_verified", False)),
        )


__all__ = ["AuthService"]
