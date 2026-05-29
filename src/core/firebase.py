"""Firebase Admin SDK integration.

The Admin SDK is sync. To avoid blocking the event loop, all network-touching
calls are dispatched to a worker thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from src.core.config import Settings, get_settings
from src.core.exceptions import AuthError
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
                "FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON."
            )

        options: dict[str, Any] = {}
        if self._settings.FIREBASE_PROJECT_ID:
            options["projectId"] = self._settings.FIREBASE_PROJECT_ID

        self._app = firebase_admin.initialize_app(cred, options or None)
        logger.info("firebase_initialised")

    def shutdown(self) -> None:
        if self._app is None:
            return
        firebase_admin.delete_app(self._app)
        self._app = None
        logger.info("firebase_shutdown")

    def _load_credentials(self) -> credentials.Base | None:
        if self._settings.FIREBASE_CREDENTIALS_PATH is not None:
            path = self._settings.FIREBASE_CREDENTIALS_PATH
            if not path.exists():
                logger.warning("firebase_credentials_path_missing", path=str(path))
                return None
            return credentials.Certificate(str(path))

        if self._settings.FIREBASE_CREDENTIALS_JSON:
            try:
                data = json.loads(self._settings.FIREBASE_CREDENTIALS_JSON)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "FIREBASE_CREDENTIALS_JSON is not valid JSON."
                ) from exc
            return credentials.Certificate(data)

        return None

    # ------------------------------------------------------------------ auth
    async def verify_id_token(
        self, token: str, *, check_revoked: bool = True
    ) -> dict[str, Any]:
        """Verify a Firebase ID token. Returns the decoded claims dict.

        Raises ``AuthError`` for any verification failure. The actual SDK call
        is run in a worker thread because it performs blocking I/O on the
        first call (key fetch).
        """
        if not token:
            raise AuthError("Missing ID token.")

        try:
            decoded: dict[str, Any] = await asyncio.to_thread(
                firebase_auth.verify_id_token,
                token,
                check_revoked=check_revoked,
            )
        except firebase_auth.ExpiredIdTokenError as exc:
            raise AuthError("ID token expired.", code="token_expired") from exc
        except firebase_auth.RevokedIdTokenError as exc:
            raise AuthError("ID token revoked.", code="token_revoked") from exc
        except firebase_auth.InvalidIdTokenError as exc:
            raise AuthError("ID token is invalid.", code="token_invalid") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("firebase_verify_unexpected_failure")
            raise AuthError("Unable to verify ID token.") from exc

        return decoded

    async def revoke_refresh_tokens(self, uid: str) -> None:
        """Revoke all refresh tokens for a user (logout-everywhere)."""
        await asyncio.to_thread(firebase_auth.revoke_refresh_tokens, uid)


firebase = FirebaseAdmin()
"""Process-wide singleton."""


__all__ = ["FirebaseAdmin", "firebase"]
