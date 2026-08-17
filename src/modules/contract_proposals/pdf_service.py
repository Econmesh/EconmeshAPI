"""HTML → PDF generation for contract proposals."""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import fitz  # pymupdf

from src.modules.contract_proposals.model import ContractProposalDocument

_SAO_PAULO_OFFSET = timezone(timedelta(hours=-3))
_PDF_MARGIN_PT = 72
_MONTHS_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pdf_page_count(data: bytes) -> int:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()


def _format_price(price: float | None, negotiable: bool) -> str:
    if negotiable or price is None:
        return "A combinar"
    return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_proposal_html(doc: ContractProposalDocument) -> str:
    sections_html = ""
    for section in sorted(doc.sections, key=lambda s: s.sort_order):
        sections_html += f"""
        <h2>{section.title}</h2>
        <div class="section-body">{section.content_html}</div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #111; line-height: 1.45; }}
h1 {{ font-size: 16pt; text-align: center; margin-bottom: 24pt; }}
h2 {{ font-size: 12pt; margin-top: 18pt; margin-bottom: 8pt; border-bottom: 1px solid #ccc; padding-bottom: 4pt; }}
.section-body p {{ margin: 0 0 8pt 0; }}
.section-body ul, .section-body ol {{ margin: 0 0 8pt 18pt; }}
.closing-date {{ text-align: center; margin-top: 18pt; }}
.signatures {{ text-align: center; margin-top: 28pt; }}
.signature {{ text-align: center; margin: 0; }}
.signature-spacer {{ margin: 0; line-height: 1.6; }}
.signature-next {{ margin-top: 36pt; }}
.meta {{ color: #555; font-size: 9pt; margin-top: 24pt; }}
</style>
</head>
<body>
<h1>{doc.title}</h1>
{sections_html}
<p class="meta">Oportunidade: {doc.opportunity.title} (ID: {doc.opportunity.opportunity_id})</p>
</body>
</html>"""


def render_proposal_pdf(doc: ContractProposalDocument) -> bytes:
    """Render the proposal document to PDF bytes via PyMuPDF Story."""
    html = build_proposal_html(doc)
    story = fitz.Story(html=html)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    more = True
    while more:
        device = writer.begin_page(fitz.paper_rect("a4"))
        margin = _PDF_MARGIN_PT
        more, _ = story.place(
            fitz.paper_rect("a4") + (margin, margin, -margin, -margin)
        )
        story.draw(device)
        writer.end_page()
    writer.close()
    return _stamp_page_numbers(buffer.getvalue())


def _stamp_page_numbers(pdf_bytes: bytes) -> bytes:
    """Add right-aligned footer page numbers in ``current/total`` format."""
    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total = pdf.page_count
        for index, page in enumerate(pdf, start=1):
            rect = page.rect
            box = fitz.Rect(
                rect.width - _PDF_MARGIN_PT - 90,
                rect.height - 48,
                rect.width - _PDF_MARGIN_PT,
                rect.height - 28,
            )
            page.insert_textbox(
                box,
                f"{index}/{total}",
                fontsize=9,
                fontname="helv",
                color=(0.25, 0.25, 0.25),
                align=fitz.TEXT_ALIGN_RIGHT,
            )
        out = io.BytesIO()
        pdf.save(out, deflate=True)
        return out.getvalue()
    finally:
        pdf.close()


def build_core_sections_html(
    *,
    contractor_block: str,
    contracted_block: str,
    opportunity_title: str,
    opportunity_description: str,
    valor: str,
    prazo: str,
    opportunity_type: str | None = None,
) -> list[tuple[str, str]]:
    """Return (title, content_html) for the four fixed core minuta sections."""
    from src.modules.contract_proposals.core_sections import CORE_SECTION_DEFINITIONS
    from src.modules.contract_proposals.opportunity_contract import objeto_html, valor_html

    partes = f"""
<p><strong>CONTRATANTE:</strong> {contractor_block}</p>
<p><strong>CONTRATADA:</strong> {contracted_block}</p>
<p>De forma global denominadas <strong>PARTES</strong> ou individualmente <strong>PARTE</strong>.</p>
"""
    objeto = objeto_html(
        opportunity_type=opportunity_type,
        opportunity_title=opportunity_title,
        opportunity_description=opportunity_description,
    )
    valor_section = valor_html(opportunity_type=opportunity_type, valor=valor)
    prazo_html = f"<p>O prazo para execução será de <strong>{prazo}</strong>.</p>"
    contents = {
        "partes": partes,
        "objeto": objeto,
        "valor": valor_section,
        "prazo": prazo_html,
    }
    return [
        (item["title"], contents[item["key"]])
        for item in CORE_SECTION_DEFINITIONS
    ]


def _sao_paulo_tz():
    try:
        return ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        return _SAO_PAULO_OFFSET


def format_foro_date(when: datetime | None = None) -> tuple[int, str, int]:
    """Return (day, month_name, year) in America/Sao_Paulo."""
    tz = _sao_paulo_tz()
    dt = when or datetime.now(tz)
    dt = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
    return dt.day, _MONTHS_PT[dt.month - 1], dt.year


def build_foro_html(
    *,
    city: str | None,
    state: str | None,
    contractor_legal_name: str,
    contracted_legal_name: str,
    signed_at: datetime | None = None,
) -> str:
    """Build the fixed Foro closing section HTML."""
    cidade = (city or "").strip() or "[cidade]"
    uf = (state or "").strip().upper() or "[UF]"
    day, month, year = format_foro_date(signed_at)
    contratante = (contractor_legal_name or "").strip() or "[razão social da contratante]"
    contratada = (contracted_legal_name or "").strip() or "[razão social da contratada]"
    return (
        f"<p>As partes elegem o foro da Comarca de <strong>{cidade}</strong> - "
        f"<strong>{uf}</strong>, para dirimir quaisquer dúvidas deste Instrumento, "
        "renunciando a qualquer outro por mais privilegiado que seja.</p>"
        "<p>E, por estarem justas e contratadas, firmam o presente em 2 (duas) vias "
        "de igual teor, juntamente com 2 (duas) testemunhas.</p>"
        f'<p class="closing-date">{cidade}- {uf}, {day} de {month} de {year}.</p>'
        '<div class="signatures">'
        f'<p class="signature">____________________________________<br/>{contratante}</p>'
        '<p class="signature-spacer"><br/><br/><br/><br/></p>'
        f'<p class="signature signature-next">____________________________________<br/>{contratada}</p>'
        "</div>"
    )


__all__ = [
    "build_core_sections_html",
    "build_foro_html",
    "build_proposal_html",
    "format_foro_date",
    "pdf_page_count",
    "render_proposal_pdf",
    "sha256_bytes",
]
