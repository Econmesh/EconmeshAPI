"""Fixed automatic minuta sections (system core)."""

from __future__ import annotations

from typing import TypedDict


class CoreSectionDefinition(TypedDict):
    key: str
    title: str
    description: str
    sort_order: int


CORE_SECTION_DEFINITIONS: tuple[CoreSectionDefinition, ...] = (
    {
        "key": "partes",
        "title": "Das Partes",
        "description": (
            "Identifica as empresas contratante e contratada (razão social, CNPJ, "
            "endereço, representante legal e contatos). É a primeira seção da minuta, "
            "obrigatória e preenchida automaticamente com os dados das empresas "
            "participantes da negociação."
        ),
        "sort_order": 0,
    },
    {
        "key": "objeto",
        "title": "Do Objeto",
        "description": (
            "Descreve o objeto do contrato com base na oportunidade negociada "
            "(título e descrição). Preenchida automaticamente e não pode ser "
            "alterada, excluída ou reordenada pelo administrador."
        ),
        "sort_order": 1,
    },
    {
        "key": "valor",
        "title": "Do Valor",
        "description": (
            "Informa o valor acordado para a execução do contrato, ou indica "
            "que o valor é a combinar. Gerada automaticamente a partir dos dados "
            "da oportunidade e da minuta."
        ),
        "sort_order": 2,
    },
    {
        "key": "prazo",
        "title": "Do Prazo",
        "description": (
            "Define o prazo de execução do contrato. Preenchida automaticamente "
            "com o prazo informado na minuta/oportunidade."
        ),
        "sort_order": 3,
    },
)

CORE_SECTION_COUNT = len(CORE_SECTION_DEFINITIONS)

# Legacy titles that may exist on older minutas
_CORE_TITLE_ALIASES: dict[str, str] = {
    "das partes": "Das Partes",
    "objeto": "Do Objeto",
    "do objeto": "Do Objeto",
    "valor": "Do Valor",
    "do valor": "Do Valor",
    "prazo": "Do Prazo",
    "do prazo": "Do Prazo",
}


def normalize_core_title(title: str) -> str | None:
    """Return canonical core title if ``title`` matches a core section."""
    key = title.strip().lower()
    if key in _CORE_TITLE_ALIASES:
        return _CORE_TITLE_ALIASES[key]
    for item in CORE_SECTION_DEFINITIONS:
        if item["title"].lower() == key:
            return item["title"]
    return None


def core_title_sort_order(title: str) -> int | None:
    canonical = normalize_core_title(title)
    if canonical is None:
        return None
    for item in CORE_SECTION_DEFINITIONS:
        if item["title"] == canonical:
            return item["sort_order"]
    return None


__all__ = [
    "CORE_SECTION_COUNT",
    "CORE_SECTION_DEFINITIONS",
    "CoreSectionDefinition",
    "core_title_sort_order",
    "normalize_core_title",
]
