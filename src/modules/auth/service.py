"""Business rules for authentication / identity sync."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.config import Settings, get_settings
from src.core.exceptions import AuthError, NotFoundError
from src.core.firebase import FirebaseAdmin, firebase
from src.core.logging import get_logger
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schema import (
    LoginResponse,
    MeResponse,
    TokenIntrospectionResponse,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

_SESSION_KEY_PREFIX = "auth:session:"
_REVOCATION_KEY_PREFIX = "auth:revoked:"


class AuthService:
    """Orchestrates Firebase verification, user sync, and session caching."""

    def __init__(
        self,
        *,
        repository: AuthRepository,
        redis_client: Redis,
        firebase_client: FirebaseAdmin | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._repo = repository
        self._redis = redis_client
        self._firebase = firebase_client or firebase
        self._settings = settings or get_settings()

    # ---------------------------------------------------------------- login
    async def login_with_id_token(self, id_token: str) -> LoginResponse:
        """Verify a Firebase ID token, upsert the user, cache the session."""
        claims = await self._firebase.verify_id_token(id_token)
        await self._guard_not_revoked(str(claims["uid"]))

        user = await self._repo.upsert_from_firebase(claims)
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
        """Mark the session as revoked in Redis and drop the cached identity."""
        await self._redis.delete(self._session_key(firebase_uid))
        await self._redis.set(
            self._revocation_key(firebase_uid),
            "1",
            ex=self._settings.SESSION_TTL_SECONDS,
        )
        logger.info("auth_logout", firebase_uid=firebase_uid)

    async def revoke_all_sessions(self, firebase_uid: str) -> None:
        """Revoke Firebase refresh tokens AND local sessions (logout-everywhere)."""
        await self._firebase.revoke_refresh_tokens(firebase_uid)
        await self.logout(firebase_uid)
        logger.warning("auth_revoke_all", firebase_uid=firebase_uid)

    # ---------------------------------------------------------------- helpers
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

    async def _guard_not_revoked(self, firebase_uid: str) -> None:
        if await self._redis.exists(self._revocation_key(firebase_uid)):
            raise AuthError("Session was revoked. Please sign in again.", code="session_revoked")

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
            picture=user.picture,
            email_verified=user.email_verified,
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
