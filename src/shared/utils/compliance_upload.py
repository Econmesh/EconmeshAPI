"""Upload helper for company compliance documents (PDF / JPEG / PNG)."""

from __future__ import annotations

from uuid import UUID

from fastapi import UploadFile

from src.core.exceptions import ValidationAppError
from src.core.firebase import FirebaseAdmin, firebase
from src.modules.companies.model import CompanyComplianceFile
from src.shared.utils.image_upload import extension_from_filename
from src.shared.utils.storage_keys import company_doc_storage_key

ALLOWED_COMPLIANCE_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "image/jpeg",
    "image/png",
}
MAX_COMPLIANCE_BYTES = 10 * 1024 * 1024

_EXT_BY_TYPE = {
    "application/pdf": "pdf",
    "application/x-pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
}


def _resolve_content_type(file: UploadFile) -> str:
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type in ALLOWED_COMPLIANCE_TYPES:
        return content_type
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf"):
        return "application/pdf"
    if filename.endswith(".jpg") or filename.endswith(".jpeg"):
        return "image/jpeg"
    if filename.endswith(".png"):
        return "image/png"
    raise ValidationAppError(
        "Unsupported document type. Use PDF, JPEG or PNG.",
        code="invalid_content_type",
    )


async def upload_compliance_file(
    file: UploadFile,
    *,
    owner_user_id: UUID,
    firebase_client: FirebaseAdmin | None = None,
) -> CompanyComplianceFile:
    """Validate and upload a compliance document; returns metadata for persistence."""
    content_type = _resolve_content_type(file)
    data = await file.read()
    if not data:
        raise ValidationAppError("Empty file.", code="empty_file")
    if len(data) > MAX_COMPLIANCE_BYTES:
        raise ValidationAppError(
            f"Document exceeds {MAX_COMPLIANCE_BYTES // (1024 * 1024)} MB limit.",
            code="file_too_large",
        )

    extension = extension_from_filename(file.filename or "")
    if extension in {"bin", ""}:
        extension = _EXT_BY_TYPE.get(content_type, "bin")
    storage_key = company_doc_storage_key(owner_user_id, extension)
    client = firebase_client or firebase
    public_url = await client.upload_storage_bytes(
        storage_key,
        data,
        content_type=content_type,
    )
    return CompanyComplianceFile(
        storage_key=storage_key,
        public_url=public_url,
        filename=file.filename or f"document.{extension}",
        content_type=content_type,
    )


__all__ = [
    "ALLOWED_COMPLIANCE_TYPES",
    "MAX_COMPLIANCE_BYTES",
    "upload_compliance_file",
]
