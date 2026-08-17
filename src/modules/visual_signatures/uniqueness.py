"""Global uniqueness for automatically generated visual signatures."""

from __future__ import annotations

import unicodedata

from src.core.crypto import keyed_hmac_hex
from src.modules.visual_signatures.model import VisualSignatureKind


def normalize_source_text(text: str) -> str:
    """NFC-normalize and collapse internal whitespace, preserving case and marks."""
    collapsed = " ".join(text.split())
    return unicodedata.normalize("NFC", collapsed)


def uniqueness_hmac(
    kind: VisualSignatureKind | str,
    source_text: str,
    font_id: str,
) -> str:
    """Keyed hash of kind + characters (order preserved) + font."""
    kind_value = kind.value if isinstance(kind, VisualSignatureKind) else kind
    message = f"{kind_value}|{normalize_source_text(source_text)}|{font_id}"
    return keyed_hmac_hex(message)


__all__ = ["normalize_source_text", "uniqueness_hmac"]
