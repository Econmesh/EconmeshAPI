"""Shared helpers for image uploads via the API (avoids browser CORS to GCS)."""

from __future__ import annotations

from fastapi import UploadFile

from src.core.exceptions import ConflictError
from src.core.firebase import firebase

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def extension_from_filename(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"


async def upload_image_file(
    file: UploadFile,
    *,
    allowed_types: set[str],
    storage_key: str,
) -> str:
    """Validate and upload an image; returns the public Storage URL."""
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in allowed_types:
        raise ConflictError(
            "Unsupported image type.",
            code="invalid_content_type",
        )

    data = await file.read()
    if not data:
        raise ConflictError("Empty file.", code="empty_file")
    if len(data) > MAX_IMAGE_BYTES:
        raise ConflictError(
            f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit.",
            code="file_too_large",
        )

    return await firebase.upload_storage_bytes(
        storage_key,
        data,
        content_type=content_type,
    )


__all__ = ["MAX_IMAGE_BYTES", "extension_from_filename", "upload_image_file"]
