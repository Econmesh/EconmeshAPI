"""Lightweight helpers to harden user inputs against injection / abuse.

Pydantic does the heavy lifting via strong typing + ``constr``/``EmailStr``,
but these helpers cover common cases (Mongo operator-injection in free-form
filters, control-character stripping, etc.).
"""

from __future__ import annotations

import re
from typing import Any

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control_chars(value: str) -> str:
    """Remove ASCII control characters (preserves \\n and \\t)."""
    return _CONTROL_CHARS_RE.sub("", value)


def clean_str(value: str, *, max_length: int = 10_000) -> str:
    """Defensive trim + length cap + control-char strip."""
    cleaned = strip_control_chars(value).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def safe_mongo_filter(filter_dict: dict[str, Any]) -> dict[str, Any]:
    """Strip Mongo operator keys (``$...``) that did not come from trusted code.

    Useful when accepting filters from untrusted query strings.
    """
    return {
        k: v
        for k, v in filter_dict.items()
        if not (isinstance(k, str) and k.startswith("$"))
    }


__all__ = ["clean_str", "safe_mongo_filter", "strip_control_chars"]
