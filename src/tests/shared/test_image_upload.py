"""Tests for shared image upload helpers."""

from __future__ import annotations

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.core.exceptions import ConflictError
from src.shared.utils.image_upload import MAX_IMAGE_BYTES, upload_image_file

pytestmark = pytest.mark.unit


async def test_upload_image_file_rejects_unsupported_type() -> None:
    file = UploadFile(
        filename="doc.pdf",
        file=_BytesIO(b"%PDF"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(ConflictError, match="Unsupported image type"):
        await upload_image_file(
            file,
            allowed_types={"image/jpeg"},
            storage_key="econmesh/images/test/doc.pdf",
        )


async def test_upload_image_file_rejects_empty_file() -> None:
    file = UploadFile(
        filename="empty.jpg",
        file=_BytesIO(b""),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    with pytest.raises(ConflictError, match="Empty file"):
        await upload_image_file(
            file,
            allowed_types={"image/jpeg"},
            storage_key="econmesh/images/test/empty.jpg",
        )


async def test_upload_image_file_rejects_oversized_file() -> None:
    file = UploadFile(
        filename="big.jpg",
        file=_BytesIO(b"x" * (MAX_IMAGE_BYTES + 1)),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    with pytest.raises(ConflictError, match="exceeds"):
        await upload_image_file(
            file,
            allowed_types={"image/jpeg"},
            storage_key="econmesh/images/test/big.jpg",
        )


class _BytesIO:
    """Minimal async file-like object for UploadFile tests."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self._pos :]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    async def seek(self, pos: int) -> None:
        self._pos = pos
