"""Identifier helpers.

Public identifiers are always UUIDs (never Mongo ObjectId) so the storage
layer can be swapped without leaking implementation details. UUIDv7 is used
when available because it embeds a monotonically increasing timestamp,
giving good index locality in MongoDB.
"""

from __future__ import annotations

import uuid


def new_uuid() -> uuid.UUID:
    """Time-ordered UUIDv7 if the runtime supports it (Python 3.14+), else v4."""
    if hasattr(uuid, "uuid7"):
        return uuid.uuid7()  # type: ignore[attr-defined]
    return uuid.uuid4()


def new_uuid_str() -> str:
    return str(new_uuid())


__all__ = ["new_uuid", "new_uuid_str"]
