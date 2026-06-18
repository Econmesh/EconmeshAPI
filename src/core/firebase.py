"""Firebase Admin SDK integration.

Supports two Firebase projects:
- **Auth** — verify ID tokens, create/manage users (``FIREBASE_CREDENTIALS_*``).
- **Storage** — presigned image uploads (``FIREBASE_STORAGE_*``).

The Admin SDK is sync. To avoid blocking the event loop, all network-touching
calls are dispatched to a worker thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import firebase_admin
from firebase_admin import App
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, storage

from src.core.config import FirebaseCredentialsSource, Settings, get_settings
from src.core.exceptions import AuthError, ConflictError, ExternalServiceError, NotFoundError
from src.core.logging import get_logger

logger = get_logger(__name__)

_AUTH_APP_NAME = "firebase-auth"
_STORAGE_APP_NAME = "firebase-storage"


class FirebaseAdmin:
    """Thin async wrapper around the Firebase Admin SDK."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._auth_app: App | None = None
        self._storage_app: App | None = None

    # -------------------------------------------------------------- lifecycle
    def init(self) -> None:
        """Initialise the Admin SDK exactly once (auth + optional storage apps)."""
        if self._auth_app is not None:
            return

        auth_cred = self._load_credentials(
            source=self._settings.FIREBASE_CREDENTIALS_SOURCE,
            path=self._settings.FIREBASE_CREDENTIALS_PATH,
            json_raw=self._settings.FIREBASE_CREDENTIALS_JSON,
            label="auth",
        )
        if auth_cred is None:
            if self._settings.is_test:
                logger.warning("firebase_skipped_in_test_env")
                return
            raise RuntimeError(
                "Firebase Auth credentials are not configured. Set "
                "FIREBASE_CREDENTIALS_SOURCE=path with FIREBASE_CREDENTIALS_PATH, or "
                "FIREBASE_CREDENTIALS_SOURCE=json with FIREBASE_CREDENTIALS_JSON."
            )

        auth_options: dict[str, Any] = {}
        if self._settings.FIREBASE_PROJECT_ID:
            auth_options["projectId"] = self._settings.FIREBASE_PROJECT_ID

        self._auth_app = firebase_admin.initialize_app(
            auth_cred,
            auth_options or None,
            name=_AUTH_APP_NAME,
        )
        logger.info("firebase_auth_initialised", project_id=self._settings.FIREBASE_PROJECT_ID)

        if self._settings.FIREBASE_STORAGE_BUCKET:
            self._init_storage_app(auth_cred)

        logger.info("firebase_initialised")

    def _init_storage_app(self, auth_cred: credentials.Base) -> None:
        storage_source = (
            self._settings.FIREBASE_STORAGE_CREDENTIALS_SOURCE
            or self._settings.FIREBASE_CREDENTIALS_SOURCE
        )
        storage_cred = self._load_credentials(
            source=storage_source,
            path=self._settings.FIREBASE_STORAGE_CREDENTIALS_PATH,
            json_raw=self._settings.FIREBASE_STORAGE_CREDENTIALS_JSON,
            label="storage",
        )
        if storage_cred is None:
            storage_cred = auth_cred
            logger.info("firebase_storage_credentials_fallback_to_auth")

        storage_options: dict[str, Any] = {
            "storageBucket": self._settings.FIREBASE_STORAGE_BUCKET,
        }
        if self._settings.FIREBASE_STORAGE_PROJECT_ID:
            storage_options["projectId"] = self._settings.FIREBASE_STORAGE_PROJECT_ID

        self._storage_app = firebase_admin.initialize_app(
            storage_cred,
            storage_options,
            name=_STORAGE_APP_NAME,
        )
        logger.info(
            "firebase_storage_initialised",
            bucket=self._settings.FIREBASE_STORAGE_BUCKET,
            project_id=self._settings.FIREBASE_STORAGE_PROJECT_ID,
        )

    def shutdown(self) -> None:
        for app in (self._storage_app, self._auth_app):
            if app is None:
                continue
            firebase_admin.delete_app(app)
        self._storage_app = None
        self._auth_app = None
        logger.info("firebase_shutdown")

    def _load_credentials(
        self,
        *,
        source: FirebaseCredentialsSource,
        path: Path | None,
        json_raw: str | None,
        label: str,
    ) -> credentials.Base | None:
        if source is FirebaseCredentialsSource.JSON:
            return self._load_credentials_from_json(json_raw, label=label)
        return self._load_credentials_from_path(path, label=label)

    def _load_credentials_from_path(
        self, path: Path | None, *, label: str
    ) -> credentials.Base | None:
        if path is None:
            logger.warning("firebase_credentials_path_not_set", label=label)
            return None
        if not path.exists():
            env_hint = (
                "FIREBASE_CREDENTIALS_PATH"
                if label == "auth"
                else "FIREBASE_STORAGE_CREDENTIALS_PATH"
            )
            raise RuntimeError(
                f"Firebase {label} credentials file not found at {path}. "
                f"Check {env_hint} or use json source."
            )
        logger.info("firebase_credentials_loaded", source="path", label=label, path=str(path))
        return credentials.Certificate(str(path))

    def _load_credentials_from_json(
        self, raw: str | None, *, label: str
    ) -> credentials.Base | None:
        if not raw:
            logger.warning("firebase_credentials_json_not_set", label=label)
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            env_hint = (
                "FIREBASE_CREDENTIALS_JSON"
                if label == "auth"
                else "FIREBASE_STORAGE_CREDENTIALS_JSON"
            )
            raise RuntimeError(f"{env_hint} is not valid JSON.") from exc
        logger.info("firebase_credentials_loaded", source="json", label=label)
        return credentials.Certificate(data)

    def _require_auth_app(self) -> App:
        if self._auth_app is None:
            raise ExternalServiceError(
                "Firebase Auth is not initialised.",
                code="firebase_not_initialised",
            )
        return self._auth_app

    def _require_storage_app(self) -> App:
        if self._storage_app is None:
            raise ExternalServiceError(
                "Firebase Storage is not configured.",
                code="storage_not_configured",
            )
        return self._storage_app

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
        auth_app = self._require_auth_app()

        try:
            decoded: dict[str, Any] = await asyncio.to_thread(
                firebase_auth.verify_id_token,
                token,
                check_revoked=check_revoked,
                clock_skew_seconds=skew,
                app=auth_app,
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
        await asyncio.to_thread(
            firebase_auth.revoke_refresh_tokens, uid, app=self._require_auth_app()
        )

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
        auth_app = self._require_auth_app()
        try:
            return await asyncio.to_thread(
                firebase_auth.create_user,
                email=email,
                password=password,
                display_name=display_name,
                email_verified=email_verified,
                disabled=disabled,
                app=auth_app,
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
        await asyncio.to_thread(
            firebase_auth.set_custom_user_claims,
            uid,
            claims,
            app=self._require_auth_app(),
        )

    async def update_user(self, uid: str, **fields: Any) -> firebase_auth.UserRecord:
        """Patch a Firebase user (e.g. ``email_verified=True``, ``disabled=...``)."""
        auth_app = self._require_auth_app()
        try:
            return await asyncio.to_thread(
                firebase_auth.update_user, uid, app=auth_app, **fields
            )
        except firebase_auth.UserNotFoundError as exc:
            raise NotFoundError("Firebase user not found.", code="user_not_found") from exc

    async def get_user_by_email(self, email: str) -> firebase_auth.UserRecord | None:
        """Return the Firebase user for an email, or ``None`` if absent."""
        auth_app = self._require_auth_app()
        try:
            return await asyncio.to_thread(
                firebase_auth.get_user_by_email, email, app=auth_app
            )
        except firebase_auth.UserNotFoundError:
            return None

    async def delete_user(self, uid: str) -> None:
        """Delete a Firebase identity (used to roll back a failed registration)."""
        auth_app = self._require_auth_app()
        try:
            await asyncio.to_thread(firebase_auth.delete_user, uid, app=auth_app)
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

    def _public_storage_url(self, storage_key: str, *, token: str | None = None) -> str:
        bucket = self._storage_bucket_name()
        encoded = quote(storage_key, safe="")
        url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o/{encoded}?alt=media"
        )
        if token:
            return f"{url}&token={token}"
        return url

    def _new_download_token(self) -> str:
        return str(uuid.uuid4())

    async def presign_storage_upload(
        self,
        storage_key: str,
        *,
        content_type: str,
        expires_in: int = 900,
    ) -> tuple[str, str]:
        """Return a signed PUT URL and the public download URL for a storage key."""
        bucket_name = self._storage_bucket_name()
        storage_app = self._require_storage_app()

        def _generate() -> str:
            bucket = storage.bucket(bucket_name, app=storage_app)
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

    async def upload_storage_bytes(
        self,
        storage_key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> str:
        """Upload bytes to Storage and return the public download URL."""
        bucket_name = self._storage_bucket_name()
        storage_app = self._require_storage_app()
        download_token = self._new_download_token()

        def _upload() -> None:
            bucket = storage.bucket(bucket_name, app=storage_app)
            blob = bucket.blob(storage_key)
            blob.metadata = {"firebaseStorageDownloadTokens": download_token}
            blob.upload_from_string(data, content_type=content_type)

        try:
            await asyncio.to_thread(_upload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("firebase_storage_upload_failed")
            raise ExternalServiceError(
                "Unable to upload file.",
                code="storage_upload_failed",
            ) from exc

        return self._public_storage_url(storage_key, token=download_token)


firebase = FirebaseAdmin()
"""Process-wide singleton."""


__all__ = ["FirebaseAdmin", "firebase"]
