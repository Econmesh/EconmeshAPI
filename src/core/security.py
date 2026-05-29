"""Security primitives: password hashing, secure tokens, constant-time compare.

Firebase is the source of truth for end-user authentication, so this module
intentionally focuses on internal needs (service-to-service tokens, API keys
for IoT devices, password hashing for non-Firebase legacy flows, etc.).
"""

from __future__ import annotations

import hmac
import secrets

import bcrypt

DEFAULT_BCRYPT_ROUNDS: int = 12


def hash_password(password: str, *, rounds: int = DEFAULT_BCRYPT_ROUNDS) -> str:
    """Hash a password with bcrypt; returns the salted hash as a UTF-8 string."""
    if not password:
        raise ValueError("password must be a non-empty string")
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def generate_secret_token(num_bytes: int = 32) -> str:
    """Cryptographically secure URL-safe token (for API keys, session IDs)."""
    return secrets.token_urlsafe(num_bytes)


def constant_time_compare(a: str, b: str) -> bool:
    """Wrap :func:`hmac.compare_digest` for string inputs."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


__all__ = [
    "constant_time_compare",
    "generate_secret_token",
    "hash_password",
    "verify_password",
]
