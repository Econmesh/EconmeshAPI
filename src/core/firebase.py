"""Firebase Admin SDK integration.

The Admin SDK is sync. To avoid blocking the event loop, all network-touching
calls are dispatched to a worker thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, storage

from src.core.config import FirebaseCredentialsSource, Settings, get_settings
from src.core.exceptions import AuthError, ConflictError, ExternalServiceError, NotFoundError
from src.core.logging import get_logger

logger = get_logger(__name__)


class FirebaseAdmin:
    """Thin async wrapper around the Firebase Admin SDK."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._app: firebase_admin.App | None = None

    # -------------------------------------------------------------- lifecycle
    def init(self) -> None:
        """Initialise the Admin SDK exactly once."""
        if self._app is not None:
            return

        cred = self._load_credentials()
        if cred is None:
            if self._settings.is_test:
                logger.warning("firebase_skipped_in_test_env")
                return
            raise RuntimeError(
                "Firebase credentials are not configured. Set "
                "FIREBASE_CREDENTIALS_SOURCE=path with FIREBASE_CREDENTIALS_PATH, or "
                "FIREBASE_CREDENTIALS_SOURCE=json with FIREBASE_CREDENTIALS_JSON."
            )

        options: dict[str, Any] = {}
        if self._settings.FIREBASE_PROJECT_ID:
            options["projectId"] = self._settings.FIREBASE_PROJECT_ID
        if self._settings.FIREBASE_STORAGE_BUCKET:
            options["storageBucket"] = self._settings.FIREBASE_STORAGE_BUCKET

        self._app = firebase_admin.initialize_app(cred, options or None)
        logger.info("firebase_initialised")

    def shutdown(self) -> None:
        if self._app is None:
            return
        firebase_admin.delete_app(self._app)
        self._app = None
        logger.info("firebase_shutdown")

    def _load_credentials(self) -> credentials.Base | None:
        source = self._settings.FIREBASE_CREDENTIALS_SOURCE
        if source is FirebaseCredentialsSource.JSON:
            return self._load_credentials_from_json()
        return self._load_credentials_from_path()

    def _load_credentials_from_path(self) -> credentials.Base | None:
        path = self._settings.FIREBASE_CREDENTIALS_PATH
        if path is None:
            logger.warning("firebase_credentials_path_not_set")
            return None
        if not path.exists():
            raise RuntimeError(
                f"Firebase credentials file not found at {path}. "
                "Check FIREBASE_CREDENTIALS_PATH or set FIREBASE_CREDENTIALS_SOURCE=json."
            )
        logger.info("firebase_credentials_loaded", source="path", path=str(path))
        return credentials.Certificate(str(path))

    def _load_credentials_from_json(self) -> credentials.Base | None:
        raw = self._settings.FIREBASE_CREDENTIALS_JSON
        if not raw:
            logger.warning("firebase_credentials_json_not_set")
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "FIREBASE_CREDENTIALS_JSON is not valid JSON."
            ) from exc
        logger.info("firebase_credentials_loaded", source="json")
        return credentials.Certificate(data)

    # ------------------------------------------------------------------ auth
    async def verify_id_token(
        self,
        token: str,
        *,
        check_revoked: bool = True,
        clock_skew_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Verify a Firebase ID token. Returns the decoded claims dict.

        Raises ``AuthError`` for any verification failure. The actual SDK call
        is run in a worker thread because it performs blocking I/O on the
        first call (key fetch).
        """
        if not token:
            raise AuthError("Missing ID token.")

        skew = (
            self._settings.FIREBASE_CLOCK_SKEW_SECONDS
            if clock_skew_seconds is None
            else clock_skew_seconds
        )

        try:
            decoded: dict[str, Any] = await asyncio.to_thread(
                firebase_auth.verify_id_token,
                token,
                check_revoked=check_revoked,
                clock_skew_seconds=skew,
            )
        except firebase_auth.ExpiredIdTokenError as exc:
            raise AuthError("ID token expired.", code="token_expired") from exc
        except firebase_auth.RevokedIdTokenError as exc:
            raise AuthError("ID token revoked.", code="token_revoked") from exc
        except firebase_auth.InvalidIdTokenError as exc:
            logger.warning(
                "firebase_token_invalid",
                error=str(exc),
                cause=str(exc.cause) if exc.cause else None,
            )
            raise AuthError("ID token is invalid.", code="token_invalid") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("firebase_verify_unexpected_failure")
            raise AuthError("Unable to verify ID token.") from exc

        return decoded

    async def revoke_refresh_tokens(self, uid: str) -> None:
        """Revoke all refresh tokens for a user (logout-everywhere)."""
        await asyncio.to_thread(firebase_auth.revoke_refresh_tokens, uid)

    # ------------------------------------------------------- user management
    async def create_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        email_verified: bool = False,
        disabled: bool = False,
    ) -> firebase_auth.UserRecord:
        """Create a Firebase identity (email/password). Raises on conflicts."""
        try:
            return await asyncio.to_thread(
                firebase_auth.create_user,
                email=email,
                password=password,
                display_name=display_name,
                email_verified=email_verified,
                disabled=disabled,
            )
        except firebase_auth.EmailAlreadyExistsError as exc:
            raise ConflictError(
                "An account with this email already exists.",
                code="email_already_exists",
            ) from exc
        except ValueError as exc:
            # Raised by the SDK for malformed inputs (weak password, bad email, …).
            raise AuthError(str(exc), code="invalid_credentials") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("firebase_create_user_failed")
            raise ExternalServiceError("Unable to create the account.") from exc

    async def set_custom_user_claims(self, uid: str, claims: dict[str, Any]) -> None:
        """Attach custom claims (e.g. ``role``) to a Firebase user."""
        await asyncio.to_thread(firebase_auth.set_custom_user_claims, uid, claims)

    async def update_user(self, uid: str, **fields: Any) -> firebase_auth.UserRecord:
        """Patch a Firebase user (e.g. ``email_verified=True``, ``disabled=...``)."""
        try:
            return await asyncio.to_thread(firebase_auth.update_user, uid, **fields)
        except firebase_auth.UserNotFoundError as exc:
            raise NotFoundError("Firebase user not found.", code="user_not_found") from exc

    async def get_user_by_email(self, email: str) -> firebase_auth.UserRecord | None:
        """Return the Firebase user for an email, or ``None`` if absent."""
        try:
            return await asyncio.to_thread(firebase_auth.get_user_by_email, email)
        except firebase_auth.UserNotFoundError:
            return None

    async def delete_user(self, uid: str) -> None:
        """Delete a Firebase identity (used to roll back a failed registration)."""
        try:
            await asyncio.to_thread(firebase_auth.delete_user, uid)
        except firebase_auth.UserNotFoundError:
            return

    # -------------------------------------------------------------- storage
    def _storage_bucket_name(self) -> str:
        bucket = self._settings.FIREBASE_STORAGE_BUCKET
        if not bucket:
            raise ExternalServiceError(
                "Firebase Storage is not configured.",
                code="storage_not_configured",
            )
        return bucket

    def _public_storage_url(self, storage_key: str) -> str:
        bucket = self._storage_bucket_name()
        encoded = quote(storage_key, safe="")
        return (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o/{encoded}?alt=media"
        )

    async def presign_storage_upload(
        self,
        storage_key: str,
        *,
        content_type: str,
        expires_in: int = 900,
    ) -> tuple[str, str]:
        """Return a signed PUT URL and the public download URL for a storage key."""
        if self._app is None:
            raise ExternalServiceError(
                "Firebase is not initialised.",
                code="firebase_not_initialised",
            )

        bucket_name = self._storage_bucket_name()

        def _generate() -> str:
            bucket = storage.bucket(bucket_name)
            blob = bucket.blob(storage_key)
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expires_in),
                method="PUT",
                content_type=content_type,
            )

        try:
            upload_url = await asyncio.to_thread(_generate)
        except Exception as exc:  # noqa: BLE001
            logger.exception("firebase_storage_presign_failed")
            raise ExternalServiceError(
                "Unable to generate upload URL.",
                code="storage_presign_failed",
            ) from exc

        return upload_url, self._public_storage_url(storage_key)


firebase = FirebaseAdmin()
"""Process-wide singleton."""


__all__ = ["FirebaseAdmin", "firebase"]
