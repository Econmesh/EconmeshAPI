"""HTML → PDF generation for contract proposals."""

from __future__ import annotations

import hashlib
import io

import fitz  # pymupdf

from src.modules.contract_proposals.model import ContractProposalDocument


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
        more, _ = story.place(fitz.paper_rect("a4") + (36, 36, -36, -36))
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()


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


__all__ = [
    "build_core_sections_html",
    "build_proposal_html",
    "pdf_page_count",
    "render_proposal_pdf",
    "sha256_bytes",
]
