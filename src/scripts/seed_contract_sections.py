"""Seed default contract section templates if the collection is empty.

Run via:

    poetry run python -m src.scripts.seed_contract_sections
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from src.core.database import mongo
from src.core.logging import get_logger, setup_logging
from src.modules.contract_sections.model import (
    ContractSectionTemplateDocument,
    SectionAppliesTo,
)
from src.modules.contract_sections.repository import ContractSectionsRepository

logger = get_logger(__name__)

_DEFAULT_SECTIONS: list[tuple[str, str, int]] = [
    (
        "Confidencialidade",
        "<p>As PARTES obrigam-se a manter em sigilo todas as informações confidenciais "
        "trocadas em razão deste contrato, pelo prazo de 5 (cinco) anos.</p>",
        10,
    ),
    (
        "Responsabilidades",
        "<p>Cada PARTE será responsável pelos danos causados à outra PARTE ou a terceiros "
        "em decorrência do descumprimento de suas obrigações contratuais.</p>",
        20,
    ),
    (
        "Condições de pagamento",
        "<p>O pagamento será efetuado conforme condições acordadas entre as PARTES, "
        "mediante apresentação de nota fiscal.</p>",
        30,
    ),
    (
        "Multa contratual",
        "<p>O descumprimento de qualquer cláusula sujeitará a PARTE infratora a multa "
        "equivalente a 10% (dez por cento) do valor do contrato.</p>",
        40,
    ),
]


async def _main() -> None:
    setup_logging()
    await mongo.connect()
    try:
        repo = ContractSectionsRepository(mongo.db)
        await repo.ensure_indexes()
        deactivated = await repo.deactivate_foro_templates()
        if deactivated:
            logger.info("legacy_foro_deactivated", extra={"count": deactivated})
            print(f"Deactivated {deactivated} legacy Foro template(s).")
        existing = await repo.count_sections(active_only=False)
        if existing > 0:
            logger.info("seed_skipped", extra={"existing": existing})
            print(f"Skip seed: {existing} section(s) already exist.")
            return

        # Use a stable nil-ish UUID placeholder for system seed
        created_by = uuid4()
        for title, content_html, sort_order in _DEFAULT_SECTIONS:
            await repo.create(
                ContractSectionTemplateDocument(
                    title=title,
                    content_html=content_html,
                    contract_type=SectionAppliesTo.TODOS,
                    sort_order=sort_order,
                    created_by=created_by,
                    is_active=True,
                    is_company_editable=False,
                )
            )
        print(f"Seeded {len(_DEFAULT_SECTIONS)} contract sections.")
        logger.info("seed_done", extra={"count": len(_DEFAULT_SECTIONS)})
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(_main())
