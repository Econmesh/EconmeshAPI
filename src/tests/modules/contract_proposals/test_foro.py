"""Unit tests for the fixed Foro closing section."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import fitz
import pytest

from src.core.exceptions import ValidationAppError
from src.modules.contract_proposals.core_sections import (
    FORO_SECTION_DEFINITION,
    is_foro_title,
)
from src.modules.contract_proposals.model import (
    ContractProposalDocument,
    ContractProposalStatus,
    OpportunitySnapshot,
    PartySnapshot,
    ProposalSection,
)
from src.modules.contract_proposals.pdf_service import (
    _stamp_page_numbers,
    build_foro_html,
    format_foro_date,
)
from src.modules.contract_proposals.section_sync import (
    ensure_foro_section,
    reorder_proposal_sections,
)
from src.modules.contract_sections.model import (
    ContractSectionTemplateDocument,
    SectionAppliesTo,
)
from src.modules.platform_settings.model import ForoFillMode, PlatformSettingsDocument
from src.modules.platform_settings.schema import PlatformSettingsUpdate
from src.modules.platform_settings.service import PlatformSettingsService

pytestmark = pytest.mark.unit


def test_is_foro_title_aliases() -> None:
    assert is_foro_title("Foro")
    assert is_foro_title("Do Foro")
    assert is_foro_title("do foro")
    assert not is_foro_title("Das Partes")


def test_build_foro_html_injects_comarca_and_parties() -> None:
    signed = datetime(2026, 8, 17, 15, 0, tzinfo=timezone(timedelta(hours=-3)))
    html = build_foro_html(
        city="Campinas",
        state="sp",
        contractor_legal_name="Contratante Exemplo Ltda.",
        contracted_legal_name="Contratada Exemplo Ltda.",
        signed_at=signed,
    )
    assert "Comarca de <strong>Campinas</strong> - <strong>SP</strong>" in html
    assert "Campinas- SP, 17 de agosto de 2026." in html
    assert 'class="signatures"' in html
    assert 'class="signature"' in html
    assert "signature-next" in html
    assert "Contratante Exemplo Ltda." in html
    assert "Contratada Exemplo Ltda." in html
    assert "2 (duas) vias" in html
    assert "2 (duas) testemunhas" in html


def test_format_foro_date_uses_sao_paulo() -> None:
    signed = datetime(2026, 1, 5, 3, 0, tzinfo=UTC)
    day, month, year = format_foro_date(signed)
    assert year == 2026
    assert month == "janeiro"
    assert day == 5


def _party(name: str) -> PartySnapshot:
    return PartySnapshot(
        company_id=uuid4(),
        legal_name=name,
        tax_id="00.000.000/0001-00",
    )


def _proposal(sections: list[ProposalSection]) -> ContractProposalDocument:
    return ContractProposalDocument(
        conversation_id=uuid4(),
        opportunity_id=uuid4(),
        offerer_company_id=uuid4(),
        interested_company_id=uuid4(),
        offerer_user_id=uuid4(),
        interested_user_id=uuid4(),
        created_by_user_id=uuid4(),
        title="Minuta",
        status=ContractProposalStatus.DRAFT,
        contractor=_party("Contratante Ltda."),
        contracted=_party("Contratada Ltda."),
        opportunity=OpportunitySnapshot(
            opportunity_id=uuid4(),
            title="Opp",
            description="Desc",
            category="cat",
        ),
        sections=sections,
        foro_city="Campinas",
        foro_state="SP",
        foro_fill_mode=ForoFillMode.COMPANY,
    )


def test_reorder_places_foro_last() -> None:
    tmpl = ContractSectionTemplateDocument(
        title="Confidencialidade",
        content_html="<p>sigilo</p>",
        contract_type=SectionAppliesTo.TODOS,
        created_by=uuid4(),
        sort_order=0,
    )
    admin = ProposalSection(
        title="Confidencialidade",
        content_html="<p>sigilo</p>",
        sort_order=0,
        is_core=False,
        is_admin_managed=True,
        is_editable=False,
        template_id=tmpl.id,
    )
    custom = ProposalSection(
        title="Extra",
        content_html="<p>custom</p>",
        sort_order=1,
        is_core=False,
        is_admin_managed=False,
        is_editable=True,
    )
    foro = ProposalSection(
        title="Foro",
        content_html="<p>old</p>",
        sort_order=2,
        is_core=True,
        is_editable=False,
    )
    partes = ProposalSection(
        title="Das Partes",
        content_html="<p>partes</p>",
        sort_order=3,
        is_core=True,
        is_editable=False,
    )
    doc = _proposal([admin, custom, foro, partes])
    assert reorder_proposal_sections(doc, [tmpl]) is True
    titles = [s.title for s in doc.sections]
    assert titles[0] == "Das Partes"
    assert titles[1] == "Confidencialidade"
    assert titles[2] == "Extra"
    assert titles[-1] == FORO_SECTION_DEFINITION["title"]
    assert doc.sections[-1].is_core is True
    assert doc.sections[-1].is_editable is False


def test_ensure_foro_section_appends_when_missing() -> None:
    partes = ProposalSection(
        title="Das Partes",
        content_html="<p>partes</p>",
        sort_order=0,
        is_core=True,
        is_editable=False,
    )
    doc = _proposal([partes])
    assert ensure_foro_section(doc) is True
    assert is_foro_title(doc.sections[-1].title)
    assert "Campinas" in doc.sections[-1].content_html
    assert ensure_foro_section(doc) is False


async def test_admin_foro_mode_requires_city_and_state() -> None:
    repo = AsyncMock()
    repo.get_or_create = AsyncMock(return_value=PlatformSettingsDocument())
    service = PlatformSettingsService(repo)
    with pytest.raises(ValidationAppError):
        await service.update(PlatformSettingsUpdate(foro_fill_mode=ForoFillMode.ADMIN))


async def test_admin_foro_mode_persists_city_and_state() -> None:
    repo = AsyncMock()
    repo.get_or_create = AsyncMock(return_value=PlatformSettingsDocument())
    repo.update = AsyncMock(
        return_value=PlatformSettingsDocument(
            foro_fill_mode=ForoFillMode.ADMIN,
            foro_city="Campinas",
            foro_state="SP",
        )
    )
    service = PlatformSettingsService(repo)
    result = await service.update(
        PlatformSettingsUpdate(
            foro_fill_mode=ForoFillMode.ADMIN,
            foro_city="Campinas",
            foro_state="sp",
        )
    )
    assert result.foro_fill_mode == ForoFillMode.ADMIN
    assert result.foro_city == "Campinas"
    assert result.foro_state == "SP"
    assert repo.update.await_args.args[0]["foro_state"] == "SP"


def test_validate_for_pdf_requires_foro_city_and_state() -> None:
    from src.modules.contract_proposals.service import ContractProposalsService

    service = ContractProposalsService.__new__(ContractProposalsService)
    partes = ProposalSection(
        title="Das Partes",
        content_html="<p>partes</p>",
        sort_order=0,
        is_core=True,
        is_editable=False,
    )
    doc = _proposal([partes])
    doc.contractor.address_line = "Rua A, 1"
    doc.contractor.legal_representative = "Fulano"
    doc.contracted.address_line = "Rua B, 2"
    doc.contracted.legal_representative = "Ciclano"
    doc.foro_city = None
    doc.foro_state = None
    with pytest.raises(ValidationAppError, match="Campos obrigatórios") as exc:
        service._validate_for_pdf(doc)
    assert "Foro: cidade" in (exc.value.details or {}).get("missing", [])
    assert "Foro: estado" in (exc.value.details or {}).get("missing", [])


def test_stamp_page_numbers_uses_current_over_total() -> None:
    source = fitz.open()
    source.new_page()
    source.new_page()
    buffer = io.BytesIO()
    source.save(buffer)
    source.close()

    stamped = _stamp_page_numbers(buffer.getvalue())
    pdf = fitz.open(stream=stamped, filetype="pdf")
    try:
        assert pdf.page_count == 2
        assert "1/2" in pdf[0].get_text()
        assert "2/2" in pdf[1].get_text()
    finally:
        pdf.close()
