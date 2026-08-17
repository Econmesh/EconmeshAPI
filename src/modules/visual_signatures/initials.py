"""Initials / rubric text variants derived from a full name."""

from __future__ import annotations

from src.modules.visual_signatures.uniqueness import normalize_source_text

PARTICLES = frozenset({"da", "das", "de", "do", "dos", "e", "d"})

VARIANT_ALL = "all_initials"
VARIANT_SIGNIFICANT = "significant_initials"
VARIANT_FIRST_NAME = "first_name"

VARIANT_LABELS = {
    VARIANT_ALL: "Todas as iniciais",
    VARIANT_SIGNIFICANT: "Iniciais sem partículas",
    VARIANT_FIRST_NAME: "Primeiro nome",
}


def _tokens(name: str) -> list[str]:
    return [token for token in normalize_source_text(name).split(" ") if token]


def _is_particle(token: str) -> bool:
    stripped = token.lower().rstrip(".")
    if stripped in PARTICLES:
        return True
    return stripped.startswith("d'") or stripped.startswith("d’")


def all_initials(name: str) -> str:
    return "".join(token[0].upper() for token in _tokens(name) if token)


def significant_initials(name: str) -> str:
    return "".join(
        token[0].upper() for token in _tokens(name) if token and not _is_particle(token)
    )


def first_name(name: str) -> str:
    tokens = _tokens(name)
    return tokens[0] if tokens else ""


def initials_options(name: str) -> list[dict[str, str]]:
    """Return unique rubric variants for a full name, in preference order."""
    variants = (
        (VARIANT_ALL, VARIANT_LABELS[VARIANT_ALL], all_initials(name)),
        (VARIANT_SIGNIFICANT, VARIANT_LABELS[VARIANT_SIGNIFICANT], significant_initials(name)),
        (VARIANT_FIRST_NAME, VARIANT_LABELS[VARIANT_FIRST_NAME], first_name(name)),
    )
    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for variant_id, label, text in variants:
        if not text or text in seen:
            continue
        seen.add(text)
        options.append({"id": variant_id, "label": label, "text": text})
    return options


def resolve_initials_text(name: str, variant_id: str) -> str:
    mapping = {
        VARIANT_ALL: all_initials(name),
        VARIANT_SIGNIFICANT: significant_initials(name),
        VARIANT_FIRST_NAME: first_name(name),
    }
    text = mapping.get(variant_id)
    if not text:
        raise ValueError(variant_id)
    return text


__all__ = [
    "PARTICLES",
    "VARIANT_ALL",
    "VARIANT_FIRST_NAME",
    "VARIANT_SIGNIFICANT",
    "all_initials",
    "first_name",
    "initials_options",
    "resolve_initials_text",
    "significant_initials",
]
