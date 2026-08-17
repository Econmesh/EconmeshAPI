"""PDF stamping and audit artifact generation for agreements."""

from __future__ import annotations

import hashlib
import io
from datetime import datetime

import fitz  # pymupdf

from src.modules.agreements.model import (
    AgreementDocument,
    AgreementEventDocument,
    AgreementField,
    AgreementParticipant,
    FieldType,
    ParticipantRole,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pdf_page_count(data: bytes) -> int:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()


def _role_label(role: ParticipantRole) -> str:
    labels = {
        ParticipantRole.SIGN: "Assinatura",
        ParticipantRole.APPROVE: "Aprovação",
        ParticipantRole.WITNESS: "Testemunha",
        ParticipantRole.ACKNOWLEDGE: "Reconhecimento",
        ParticipantRole.RECEIPT: "Recebimento",
    }
    return labels.get(role, "Assinatura")


def stamp_signed_pdf(
    original_pdf: bytes,
    *,
    agreement: AgreementDocument,
    participant: AgreementParticipant,
    fields: list[AgreementField],
    signed_at: datetime,
    document_hash: str,
    signature_png: bytes | None = None,
    initials_png: bytes | None = None,
) -> bytes:
    """Draw field values and an authentication block for one participant."""
    doc = fitz.open(stream=original_pdf, filetype="pdf")
    try:
        for field in fields:
            if field.page < 1 or field.page > doc.page_count:
                continue
            page = doc[field.page - 1]
            rect = page.rect
            x0 = rect.x0 + field.x * rect.width
            y0 = rect.y0 + field.y * rect.height
            x1 = x0 + field.width * rect.width
            y1 = y0 + field.height * rect.height
            box = fitz.Rect(x0, y0, x1, y1)

            if field.field_type == FieldType.SIGNATURE and signature_png:
                page.insert_image(box, stream=signature_png, keep_proportion=True)
                continue
            if field.field_type == FieldType.INITIALS and initials_png:
                page.insert_image(box, stream=initials_png, keep_proportion=True)
                continue

            label = field.value or ""
            if field.field_type == FieldType.SIGNATURE or field.field_type == FieldType.NAME:
                label = participant.name
            elif field.field_type == FieldType.CPF:
                label = participant.cpf or ""
            elif field.field_type == FieldType.JOB_TITLE:
                label = participant.job_title or ""
            elif field.field_type == FieldType.COMPANY:
                label = participant.company_name or ""
            elif field.field_type == FieldType.DATE:
                label = signed_at.strftime("%d/%m/%Y")
            elif field.field_type == FieldType.INITIALS:
                parts = participant.name.split()
                label = "".join(p[0] for p in parts[:2]).upper() if parts else ""
            elif field.field_type == FieldType.CHECKBOX:
                label = "☑" if (field.value or "").lower() in {"1", "true", "yes", "on"} else "☐"

            if label:
                page.insert_textbox(
                    box,
                    label,
                    fontsize=9,
                    color=(0.05, 0.33, 0.23),
                    align=fitz.TEXT_ALIGN_LEFT,
                )

        # Auth stamp on last page
        last = doc[-1]
        stamp_rect = fitz.Rect(
            36, last.rect.height - 140, last.rect.width - 36, last.rect.height - 36
        )
        stamp_text = (
            f"Assinatura Digital — {_role_label(participant.role)}\n"
            f"Nome: {participant.name}\n"
            f"CPF: {participant.cpf or '—'}\n"
            f"Empresa: {participant.company_name or '—'}\n"
            f"Data/Hora: {signed_at.strftime('%d/%m/%Y %H:%M:%S')} UTC\n"
            f"IP: {participant.ip or '—'}\n"
            f"Hash: {document_hash[:32]}…\n"
            f"Código: {agreement.verification_code}"
        )
        last.draw_rect(stamp_rect, color=(0.05, 0.33, 0.23), width=1)
        last.insert_textbox(
            stamp_rect + (6, 6, -6, -6),
            stamp_text,
            fontsize=8,
            color=(0.05, 0.33, 0.23),
        )

        out = io.BytesIO()
        doc.save(out, deflate=True)
        return out.getvalue()
    finally:
        doc.close()


def build_audit_report_pdf(
    *,
    agreement: AgreementDocument,
    events: list[AgreementEventDocument],
    document_hash: str,
) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page()
        y = 48
        lines = [
            "Relatório de Auditoria — EconMesh Acordos",
            f"Acordo: {agreement.title}",
            f"Código: {agreement.verification_code}",
            f"Empresa: {agreement.company_name}",
            f"Hash do documento: {document_hash}",
            f"Status: {agreement.status}",
            "",
            "Histórico:",
        ]
        for line in lines:
            page.insert_text((48, y), line, fontsize=11 if y == 48 else 9)
            y += 16

        for event in events:
            if y > 780:
                page = doc.new_page()
                y = 48
            actor = event.actor_name or "Sistema"
            company = f" ({event.actor_company_name})" if event.actor_company_name else ""
            line = (
                f"{event.created_at.strftime('%d/%m/%Y %H:%M:%S')} — "
                f"{event.event_type} — {actor}{company}"
            )
            page.insert_text((48, y), line, fontsize=8)
            y += 14

        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()


def build_certificate_pdf(
    *,
    agreement: AgreementDocument,
    document_hash: str,
) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page()
        text = (
            "Certificado de Autenticidade\n\n"
            f"Documento: {agreement.title}\n"
            f"Empresa responsável: {agreement.company_name}\n"
            f"Código de verificação: {agreement.verification_code}\n"
            f"Hash SHA-256: {document_hash}\n\n"
            "Este certificado atesta a integridade e a rastreabilidade "
            "eletrônica do acordo na plataforma EconMesh.\n"
        )
        completed = [
            p for p in agreement.participants if p.completed_at is not None
        ]
        text += "\nAssinantes:\n"
        for p in completed:
            text += (
                f"- {p.name} ({p.role}) em "
                f"{p.completed_at.strftime('%d/%m/%Y %H:%M:%S') if p.completed_at else '—'} UTC\n"
            )
        page.insert_textbox(
            fitz.Rect(48, 72, page.rect.width - 48, page.rect.height - 72),
            text,
            fontsize=11,
        )
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()


def _append_lines(doc: fitz.Document, lines: list[str], *, title: str) -> None:
    page = doc.new_page()
    y = 48
    page.insert_text((48, y), title, fontsize=12)
    y += 22
    for line in lines:
        if y > 780:
            page = doc.new_page()
            y = 48
        # Wrap long lines roughly
        chunk = line
        while len(chunk) > 110:
            page.insert_text((48, y), chunk[:110], fontsize=8)
            y += 12
            if y > 780:
                page = doc.new_page()
                y = 48
            chunk = chunk[110:]
        page.insert_text((48, y), chunk, fontsize=8)
        y += 12


def build_chat_audit_report_pdf(
    *,
    agreement: AgreementDocument,
    messages: list[dict[str, object]],
    until: datetime | None,
) -> bytes:
    doc = fitz.open()
    try:
        cutoff = (
            until.strftime("%d/%m/%Y %H:%M:%S") + " UTC" if until else "conclusão do acordo"
        )
        lines = [
            f"Acordo: {agreement.title}",
            f"Código: {agreement.verification_code}",
            f"Conversa: {agreement.conversation_id or '—'}",
            f"Período: mensagens até {cutoff}",
            "",
            "Histórico do chat:",
        ]
        if not messages:
            lines.append("(Nenhuma mensagem registrada até o momento da assinatura.)")
        for msg in messages:
            created = str(msg.get("created_at", ""))
            author = str(msg.get("author_name") or msg.get("author_role") or "Sistema")
            body = str(msg.get("body") or "").replace("\n", " ")
            msg_type = str(msg.get("message_type") or "")
            lines.append(f"{created} — [{msg_type}] {author}: {body}")
        _append_lines(
            doc,
            lines,
            title="Relatório de Auditoria do Chat — EconMesh",
        )
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()


def build_opportunity_audit_report_pdf(
    *,
    agreement: AgreementDocument,
    opportunity: dict[str, object],
) -> bytes:
    doc = fitz.open()
    try:
        lines = [
            f"Acordo: {agreement.title}",
            f"Código: {agreement.verification_code}",
            f"Oportunidade vinculada: {agreement.opportunity_id or '—'}",
            "",
            "Registro da oportunidade (como cadastrada):",
        ]
        labels = [
            ("id", "ID"),
            ("title", "Título"),
            ("description", "Descrição"),
            ("company_name", "Empresa"),
            ("opportunity_type", "Tipo"),
            ("offer_demand", "Oferta/Demanda"),
            ("category", "Categoria"),
            ("technical_detail", "Detalhe técnico"),
            ("physical_state", "Estado físico"),
            ("periodicity", "Periodicidade"),
            ("quantity", "Quantidade"),
            ("unit", "Unidade"),
            ("price", "Preço"),
            ("price_negotiable", "Preço negociável"),
            ("city", "Cidade"),
            ("state", "Estado"),
            ("purity_percent", "Pureza (%)"),
            ("is_active", "Ativa"),
            ("created_at", "Criada em"),
            ("updated_at", "Atualizada em"),
        ]
        for key, label in labels:
            if key not in opportunity:
                continue
            value = opportunity.get(key)
            if value is None or value == "":
                value = "—"
            lines.append(f"{label}: {value}")
        _append_lines(
            doc,
            lines,
            title="Relatório de Auditoria da Oportunidade — EconMesh",
        )
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()


__all__ = [
    "build_audit_report_pdf",
    "build_certificate_pdf",
    "build_chat_audit_report_pdf",
    "build_opportunity_audit_report_pdf",
    "pdf_page_count",
    "sha256_bytes",
    "stamp_signed_pdf",
]
