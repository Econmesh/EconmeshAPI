"""Tests for Firebase Storage object key builders."""

from uuid import UUID

from src.shared.utils.storage_keys import (
    avatar_storage_key,
    image_storage_key,
    logo_storage_key,
)


def test_avatar_storage_key_uses_econmesh_prefix() -> None:
    user_id = UUID("00000000-0000-4000-8000-000000000001")
    key = avatar_storage_key(user_id, "png")
    assert key.startswith("econmesh/avatars/00000000-0000-4000-8000-000000000001/")
    assert key.endswith(".png")


def test_logo_storage_key_uses_econmesh_prefix() -> None:
    key = logo_storage_key("owner-1", "jpg")
    assert key.startswith("econmesh/logos/owner-1/")
    assert key.endswith(".jpg")


def test_image_storage_key_uses_econmesh_prefix() -> None:
    key = image_storage_key("owner-2", "webp")
    assert key.startswith("econmesh/images/owner-2/")
    assert key.endswith(".webp")
