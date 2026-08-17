"""Tests for visual signature uniqueness, initials, crypto, and integrity."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from PIL import Image
from src.core.crypto import decrypt_string, encrypt_string
from src.core.exceptions import ConflictError, ValidationAppError
from src.modules.visual_signatures.initials import (
    all_initials,
    first_name,
    initials_options,
    significant_initials,
)
from src.modules.visual_signatures.model import (
    VisualSignatureDocument,
    VisualSignatureKind,
    VisualSignatureSource,
)
from src.modules.visual_signatures.renderer import process_manual_png, sha256_bytes
from src.modules.visual_signatures.service import VisualSignaturesService
from src.modules.visual_signatures.uniqueness import normalize_source_text, uniqueness_hmac
from src.shared.utils.ids import new_uuid

pytestmark = pytest.mark.unit


def test_encrypt_roundtrip() -> None:
    secret = "João Francisco da Silva"
    blob = encrypt_string(secret)
    assert blob.startswith("v1:")
    assert secret not in blob
    assert decrypt_string(blob) == secret


def test_uniqueness_hmac_differs_by_characters_and_font() -> None:
    kind = VisualSignatureKind.SIGNATURE
    joao = uniqueness_hmac(kind, "João Francisco Silva", "great_vibes")
    joao_da = uniqueness_hmac(kind, "João Francisco da Silva", "great_vibes")
    joao_other_font = uniqueness_hmac(kind, "João Francisco Silva", "allura")
    assert joao != joao_da
    assert joao != joao_other_font
    assert joao == uniqueness_hmac(kind, "João Francisco Silva", "great_vibes")


def test_uniqueness_hmac_is_nfc_stable() -> None:
    composed = "João"
    decomposed = "Joa\u0303o"
    assert normalize_source_text(composed) == normalize_source_text(decomposed)
    assert uniqueness_hmac("signature", composed, "allura") == uniqueness_hmac(
        "signature", decomposed, "allura"
    )


def test_initials_include_and_skip_particles() -> None:
    name = "João Francisco da Silva"
    assert all_initials(name) == "JFDS"
    assert significant_initials(name) == "JFS"
    assert first_name("Cleby Francisco da Silva") == "Cleby"
    assert all_initials("Cleyton Francisco da Silva") == "CFDS"
    assert significant_initials("Cleyton Francisco da Silva") == "CFS"


def test_initials_options_are_unique_by_text() -> None:
    options = initials_options("João Francisco Silva")
    texts = [item["text"] for item in options]
    assert texts[0] == "JFS"
    assert "João" in texts
    assert len(texts) == len(set(texts))


def test_automatic_render_hash_includes_font_and_text() -> None:
    from src.modules.visual_signatures.fonts import list_fonts
    from src.modules.visual_signatures.renderer import render_automatic

    fonts = list_fonts()
    if not fonts:
        pytest.skip("No signature fonts bundled")
    font_id = fonts[0].id
    created = datetime.now(UTC)
    user_id = new_uuid()
    first = render_automatic(
        "João Francisco Silva",
        font_id=font_id,
        kind=VisualSignatureKind.SIGNATURE,
        user_id=user_id,
        signature_id=new_uuid(),
        created_at=created,
    )
    second = render_automatic(
        "João Francisco da Silva",
        font_id=font_id,
        kind=VisualSignatureKind.SIGNATURE,
        user_id=user_id,
        signature_id=new_uuid(),
        created_at=created,
    )
    assert first.sha256 != second.sha256
    assert first.data.startswith(b"\x89PNG")


def test_manual_png_hash_changes_when_pixels_change() -> None:
    white = Image.new("RGB", (120, 60), (255, 255, 255))
    marked = white.copy()
    marked.putpixel((10, 10), (0, 0, 0))
    first = _png_bytes(white)
    second = _png_bytes(marked)
    user_id = new_uuid()
    created = datetime.now(UTC)
    processed_a = process_manual_png(
        first,
        kind=VisualSignatureKind.SIGNATURE,
        user_id=user_id,
        signature_id=new_uuid(),
        created_at=created,
    )
    processed_b = process_manual_png(
        second,
        kind=VisualSignatureKind.SIGNATURE,
        user_id=user_id,
        signature_id=new_uuid(),
        created_at=created,
    )
    assert processed_a.sha256 != processed_b.sha256
    assert processed_a.sha256 == sha256_bytes(processed_a.data)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _service() -> tuple[VisualSignaturesService, MagicMock, MagicMock]:
    repo = MagicMock()
    events = MagicMock()
    auth = MagicMock()
    service = VisualSignaturesService(repo, events, auth)
    return service, repo, events


@pytest.mark.asyncio
async def test_confirm_automatic_rejects_duplicate_combo(monkeypatch: pytest.MonkeyPatch) -> None:
    service, repo, _events = _service()
    user = MagicMock()
    user.id = uuid4()
    user.name = "João Francisco Silva"
    service._resolve_user = AsyncMock(return_value=user)  # noqa: SLF001
    repo.get_for_user = AsyncMock(return_value=None)
    repo.uniqueness_taken = AsyncMock(return_value=True)

    from src.modules.visual_signatures.schema import VisualSignatureConfirmRequest

    with pytest.raises(ConflictError) as exc:
        await service.confirm_automatic(
            VisualSignatureConfirmRequest(
                kind=VisualSignatureKind.SIGNATURE, font_id="great_vibes"
            ),
            firebase_uid="uid",
            ip=None,
            user_agent=None,
        )
    assert exc.value.code == "visual_signature_not_unique"


@pytest.mark.asyncio
async def test_second_artifact_of_same_kind_is_rejected() -> None:
    service, repo, _events = _service()
    user = MagicMock()
    user.id = uuid4()
    user.name = "João Francisco Silva"
    service._resolve_user = AsyncMock(return_value=user)  # noqa: SLF001
    repo.get_for_user = AsyncMock(
        return_value=VisualSignatureDocument(
            user_id=user.id,
            kind=VisualSignatureKind.SIGNATURE,
            source=VisualSignatureSource.MANUAL,
            source_text_enc=encrypt_string("João Francisco Silva"),
            storage_key="econmesh/signatures/x/a.png",
            sha256="abc",
            width=10,
            height=10,
        )
    )

    from src.modules.visual_signatures.schema import VisualSignatureConfirmRequest

    with pytest.raises(ConflictError) as exc:
        await service.confirm_automatic(
            VisualSignatureConfirmRequest(kind=VisualSignatureKind.SIGNATURE, font_id="allura"),
            firebase_uid="uid",
            ip=None,
            user_agent=None,
        )
    assert exc.value.code == "visual_signature_already_exists"


@pytest.mark.asyncio
async def test_load_png_rejects_integrity_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    service, repo, events = _service()
    doc = VisualSignatureDocument(
        user_id=uuid4(),
        kind=VisualSignatureKind.SIGNATURE,
        source=VisualSignatureSource.MANUAL,
        source_text_enc=encrypt_string("Ada"),
        storage_key="econmesh/signatures/x/a.png",
        sha256="0" * 64,
        width=10,
        height=10,
    )
    repo.get_for_user = AsyncMock(return_value=doc)
    events.create = AsyncMock()

    async def _download(_key: str) -> bytes:
        return b"tampered-bytes"

    monkeypatch.setattr(
        "src.modules.visual_signatures.service.firebase.download_storage_bytes",
        _download,
    )

    with pytest.raises(ConflictError) as exc:
        await service.load_png_for_user(doc.user_id, VisualSignatureKind.SIGNATURE)
    assert exc.value.code == "visual_signature_integrity_failed"
    events.create.assert_awaited()


@pytest.mark.asyncio
async def test_load_png_requires_existing_artifact() -> None:
    service, repo, _events = _service()
    repo.get_for_user = AsyncMock(return_value=None)
    with pytest.raises(ValidationAppError) as exc:
        await service.load_png_for_user(uuid4(), VisualSignatureKind.INITIALS)
    assert exc.value.code == "visual_signature_required"
