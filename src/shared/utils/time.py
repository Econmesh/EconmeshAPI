"""Timezone-aware time helpers — always prefer these over ``datetime.utcnow``."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current time in UTC, with tzinfo. Always use this instead of ``datetime.utcnow``."""
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    """Format an aware datetime as RFC 3339 / ISO 8601."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


__all__ = ["to_iso", "utcnow"]
