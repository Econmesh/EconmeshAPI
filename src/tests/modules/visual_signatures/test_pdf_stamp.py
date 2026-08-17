"""Tests for embedding visual signature images into stamped PDFs."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import fitz
import pytest
from PIL import Image
from src.modules.agreements.model import (
    AgreementDocument,
    AgreementField,
    AgreementFile,
    AgreementParticipant,
    FieldType,
    ParticipantKind,
)
from src.modules.agreements.pdf_service import stamp_signed_pdf
from src.shared.utils.ids import new_uuid

pytestmark = pytest.mark.unit


def _png(color: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    image = Image.new("RGB", (80, 40), (255, 255, 255))
    image.putpixel((2, 2), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _blank_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page(width=400, height=500)
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def test_stamp_signed_pdf_embeds_signature_and_initials_images() -> None:
    participant = AgreementParticipant(
        kind=ParticipantKind.EXTERNAL,
        name="Ada Lovelace",
        email="ada@example.com",
    )
    signature_field = AgreementField(
        participant_id=participant.id,
        field_type=FieldType.SIGNATURE,
        page=1,
        x=0.1,
        y=0.1,
        width=0.4,
        height=0.1,
    )
    initials_field = AgreementField(
        participant_id=participant.id,
        field_type=FieldType.INITIALS,
        page=1,
        x=0.1,
        y=0.3,
        width=0.2,
        height=0.08,
    )
    agreement = AgreementDocument(
        title="Contrato",
        company_id=new_uuid(),
        company_name="Acme",
        owner_user_id=new_uuid(),
        verification_code="ABC123XYZ789",
        original_file=AgreementFile(
            storage_key="k",
            url="https://example.com/a.pdf",
            sha256="a" * 64,
            filename="a.pdf",
        ),
        participants=[participant],
        fields=[signature_field, initials_field],
    )
    stamped = stamp_signed_pdf(
        _blank_pdf(),
        agreement=agreement,
        participant=participant,
        fields=[signature_field, initials_field],
        signed_at=datetime.now(UTC),
        document_hash="b" * 64,
        signature_png=_png((0, 0, 0)),
        initials_png=_png((10, 10, 10)),
    )
    opened = fitz.open(stream=stamped, filetype="pdf")
    try:
        images = opened[0].get_images()
        assert len(images) >= 2
    finally:
        opened.close()
