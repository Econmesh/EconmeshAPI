"""Firebase Storage object key builders.

All uploads are stored under ``econmesh/<category>/...`` in the bucket.
"""

from __future__ import annotations

from uuid import UUID

from src.shared.utils.ids import new_uuid_str

STORAGE_ROOT = "econmesh"


def build_storage_key(category: str, owner_id: UUID | str, extension: str) -> str:
    """Return a unique object key under ``econmesh/<category>/``."""
    ext = extension.lstrip(".")
    return f"{STORAGE_ROOT}/{category}/{owner_id}/{new_uuid_str()}.{ext}"


def avatar_storage_key(user_id: UUID | str, extension: str) -> str:
    return build_storage_key("avatars", user_id, extension)


def logo_storage_key(owner_user_id: UUID | str, extension: str) -> str:
    return build_storage_key("logos", owner_user_id, extension)


def image_storage_key(owner_user_id: UUID | str, extension: str) -> str:
    return build_storage_key("images", owner_user_id, extension)


__all__ = [
    "STORAGE_ROOT",
    "avatar_storage_key",
    "build_storage_key",
    "image_storage_key",
    "logo_storage_key",
]
