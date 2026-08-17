"""Field-level encryption (AES-256-GCM) and keyed HMACs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.config import get_settings

_NONCE_SIZE = 12
_VERSION_PREFIX = "v1:"


def _key() -> bytes:
    return get_settings().data_encryption_key_bytes()


def encrypt_string(plaintext: str) -> str:
    """Encrypt UTF-8 text and return a versioned, base64 ciphertext blob."""
    nonce = os.urandom(_NONCE_SIZE)
    aes = AESGCM(_key())
    ciphertext = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    packed = nonce + ciphertext
    return _VERSION_PREFIX + base64.b64encode(packed).decode("ascii")


def decrypt_string(blob: str) -> str:
    """Decrypt a blob produced by :func:`encrypt_string`."""
    if not blob.startswith(_VERSION_PREFIX):
        raise ValueError("Unsupported ciphertext version.")
    packed = base64.b64decode(blob[len(_VERSION_PREFIX) :], validate=True)
    if len(packed) <= _NONCE_SIZE:
        raise ValueError("Ciphertext is truncated.")
    nonce, ciphertext = packed[:_NONCE_SIZE], packed[_NONCE_SIZE:]
    aes = AESGCM(_key())
    return aes.decrypt(nonce, ciphertext, None).decode("utf-8")


def keyed_hmac_hex(message: str) -> str:
    """HMAC-SHA256 hex digest using the data-encryption key."""
    return hmac.new(_key(), message.encode("utf-8"), hashlib.sha256).hexdigest()


__all__ = ["decrypt_string", "encrypt_string", "keyed_hmac_hex"]
