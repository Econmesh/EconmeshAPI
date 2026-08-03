"""Unicode-friendly slug helpers for URL-safe identifiers."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MULTI_DASH_RE = re.compile(r"-{2,}")


def slugify(value: str, *, max_length: int = 120) -> str:
    """Convert ``value`` into a lowercase ASCII URL slug."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower().strip()
    dashed = _NON_ALNUM_RE.sub("-", lowered)
    collapsed = _MULTI_DASH_RE.sub("-", dashed).strip("-")
    if not collapsed:
        collapsed = "post"
    return collapsed[:max_length].rstrip("-")


__all__ = ["slugify"]
