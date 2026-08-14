"""Tests for company compliance document uploads."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.core.exceptions import ValidationAppError
from src.shared.utils.compliance_upload import MAX_COMPLIANCE_BYTES, upload_compliance_file
from src.shared.utils.ids import new_uuid

pytestmark = pytest.mark.unit


def _upload(
    name: str,
    data: bytes,
    content_type: str,
) -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(data),
        headers=Headers({"content-type": content_type}),
    )


async def test_upload_compliance_file_rejects_unsupported_type() -> None:
    file = _upload("notes.txt", b"hello", "text/plain")
    with pytest.raises(ValidationAppError) as exc:
        await upload_compliance_file(file, owner_user_id=new_uuid())
    assert exc.value.code == "invalid_content_type"


async def test_upload_compliance_file_rejects_empty_file() -> None:
    file = _upload("empty.pdf", b"", "application/pdf")
    with pytest.raises(ValidationAppError) as exc:
        await upload_compliance_file(file, owner_user_id=new_uuid())
    assert exc.value.code == "empty_file"


async def test_upload_compliance_file_rejects_oversized_file() -> None:
    file = _upload("huge.pdf", b"x" * (MAX_COMPLIANCE_BYTES + 1), "application/pdf")
    with pytest.raises(ValidationAppError) as exc:
        await upload_compliance_file(file, owner_user_id=new_uuid())
    assert exc.value.code == "file_too_large"


async def test_upload_compliance_file_stores_pdf() -> None:
    firebase = AsyncMock()
    firebase.upload_storage_bytes = AsyncMock(return_value="https://storage.example/lo.pdf")
    file = _upload("lo.pdf", b"%PDF-1.4 test", "application/pdf")
    result = await upload_compliance_file(
        file, owner_user_id=new_uuid(), firebase_client=firebase
    )
    assert result.filename == "lo.pdf"
    assert result.content_type == "application/pdf"
    assert result.public_url == "https://storage.example/lo.pdf"
    assert "company-docs" in result.storage_key
    assert result.status == "pending"
    firebase.upload_storage_bytes.assert_awaited_once()
