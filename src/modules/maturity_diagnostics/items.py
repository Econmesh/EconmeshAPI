"""Itens dinâmicos do DMC (produtos e resíduos): identificadores e compatibilidade.

Diagnósticos anteriores ao catálogo ``2026-11`` respondiam 1.1 e 1.7 como
texto livre e as demais perguntas uma única vez por empresa. ``migrate_legacy``
converte esse formato sem perda: cria um item a partir do texto da 1.1/1.7 e
move as respostas gerais das perguntas agora "por item" para esse item.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from src.modules.maturity_diagnostics.catalog import Catalog
from src.modules.maturity_diagnostics.engine import response_key
from src.modules.maturity_diagnostics.model import DiagnosticItem

ITEM_NAME_MAX = 120
ITEM_DESCRIPTION_MAX = 2000


def new_item_id() -> str:
    return uuid4().hex[:12]


def _legacy_name(text: str | None, fallback: str) -> str:
    if not text:
        return fallback
    first = next((line.strip(" -•\t") for line in text.splitlines() if line.strip()), "")
    if not first:
        return fallback
    if len(first) > ITEM_NAME_MAX:
        return first[: ITEM_NAME_MAX - 1].rstrip() + "…"
    return first


def migrate_legacy[T](
    catalog: Catalog,
    responses: Mapping[str, T],
    items: list[DiagnosticItem],
    *,
    value_of=lambda response: getattr(response, "value", response),
) -> tuple[dict[str, T], list[DiagnosticItem], bool]:
    """Converte respostas no formato antigo. Retorna ``(respostas, itens, mudou)``.

    Só atua em diagnósticos sem nenhum item cadastrado; para cada tipo de item,
    cria um único item quando há texto na pergunta de cadastro ou respostas
    gerais de perguntas que passaram a ser por item.
    """
    if items:
        return dict(responses), list(items), False
    migrated: dict[str, T] = dict(responses)
    created: list[DiagnosticItem] = []
    for meta in catalog.item_kinds:
        per_item_ids = [q.id for q in catalog.questions if q.per_item == meta.kind]
        legacy_ids = [qid for qid in per_item_ids if qid in migrated]
        list_response = migrated.get(meta.list_question_id)
        raw = value_of(list_response) if list_response is not None else None
        text = raw.strip() if isinstance(raw, str) and raw.strip() else None
        if not legacy_ids and text is None:
            continue
        item = DiagnosticItem(
            id=new_item_id(),
            kind=meta.kind,
            name=_legacy_name(text, f"{meta.label} 1"),
            description=text[:ITEM_DESCRIPTION_MAX] if text else None,
        )
        for qid in legacy_ids:
            migrated[response_key(qid, item.id)] = migrated.pop(qid)
        # O texto da pergunta de cadastro agora vive no próprio item.
        migrated.pop(meta.list_question_id, None)
        created.append(item)
    return migrated, created, bool(created)


__all__ = [
    "ITEM_DESCRIPTION_MAX",
    "ITEM_NAME_MAX",
    "migrate_legacy",
    "new_item_id",
]
