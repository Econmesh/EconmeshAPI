"""Allowlisted cursive fonts for automatic signature and rubric generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.exceptions import ValidationAppError

_FONTS_DIR = Path(__file__).resolve().parent / "fonts"


@dataclass(frozen=True, slots=True)
class SignatureFont:
    id: str
    name: str
    filename: str

    @property
    def path(self) -> Path:
        return _FONTS_DIR / self.filename


SIGNATURE_FONTS: tuple[SignatureFont, ...] = (
    SignatureFont("great_vibes", "Great Vibes", "GreatVibes-Regular.ttf"),
    SignatureFont("allura", "Allura", "Allura-Regular.ttf"),
    SignatureFont("sacramento", "Sacramento", "Sacramento-Regular.ttf"),
)

_FONTS_BY_ID = {font.id: font for font in SIGNATURE_FONTS}


def list_fonts() -> list[SignatureFont]:
    return [font for font in SIGNATURE_FONTS if font.path.is_file()]


def get_font(font_id: str) -> SignatureFont:
    font = _FONTS_BY_ID.get(font_id)
    if font is None:
        raise ValidationAppError(
            "Fonte inválida.",
            code="invalid_signature_font",
        )
    if not font.path.is_file():
        raise ValidationAppError(
            "Fonte indisponível no servidor.",
            code="signature_font_missing",
        )
    return font


__all__ = ["SIGNATURE_FONTS", "SignatureFont", "get_font", "list_fonts"]
