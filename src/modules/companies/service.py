"""Business rules for ``companies``."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import UploadFile

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.firebase import firebase
from src.core.logging import get_logger
from src.modules.auth.repository import AuthRepository
from src.modules.companies.compliance_review import document_field
from src.modules.companies.model import (
    CompanyAddress,
    CompanyDocument,
    ComplianceDocumentStatus,
)
from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.schema import (
    CompanyAddressResponse,
    CompanyComplianceFileResponse,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    LogoPresignRequest,
    LogoPresignResponse,
)
from src.shared.schemas.responses import StorageUploadResponse
from src.shared.utils.image_upload import extension_from_filename, upload_image_file
from src.shared.utils.storage_keys import logo_storage_key
from src.shared.utils.compliance_upload import upload_compliance_file
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from src.modules.companies.compliance_review import ComplianceReviewService

logger = get_logger(__name__)

_ALLOWED_LOGO_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/svg+xml",
}


class CompaniesService:
    def __init__(
        self,
        repository: CompaniesRepository,
        auth_repository: AuthRepository,
        compliance_review: ComplianceReviewService | None = None,
    ) -> None:
        self._repo = repository
        self._auth_repo = auth_repository
        self._compliance_review = compliance_review

    async def _resolve_user_id(self, firebase_uid: str) -> UUID:
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user.id

    async def _ensure_owner(self, company: CompanyDocument, owner_user_id: UUID) -> None:
        if company.owner_user_id != owner_user_id:
            raise ForbiddenError("You do not have access to this company.")

    def _to_response(self, doc: CompanyDocument) -> CompanyResponse:
        address = None
        if doc.address is not None:
            address = CompanyAddressResponse.model_validate(doc.address.model_dump())
        operating_license = None
        if doc.operating_license is not None:
            operating_license = CompanyComplianceFileResponse.model_validate(
                doc.operating_license.model_dump()
            )
        mtr_document = None
        if doc.mtr_document is not None:
            mtr_document = CompanyComplianceFileResponse.model_validate(
                doc.mtr_document.model_dump()
            )
        signature_authorization = None
        if doc.signature_authorization is not None:
            signature_authorization = CompanyComplianceFileResponse.model_validate(
                doc.signature_authorization.model_dump()
            )
        return CompanyResponse(
            id=doc.id,
            owner_user_id=doc.owner_user_id,
            legal_name=doc.legal_name,
            trade_name=doc.trade_name,
            tax_id=doc.tax_id,
            email=doc.email,
            phone=doc.phone,
            legal_representative=doc.legal_representative,
            address=address,
            country=doc.country,
            website=doc.website,
            description=doc.description,
            logo_storage_key=doc.logo_storage_key,
            logo_url=doc.logo_url,
            sector=doc.sector,
            operating_license=operating_license,
            mtr_document=mtr_document,
            signature_authorization=signature_authorization,
            is_active=doc.is_active,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def list(
        self, *, firebase_uid: str, page: int, page_size: int
    ) -> list[CompanyResponse]:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        skip = (page - 1) * page_size
        docs = await self._repo.list_for_owner(
            owner_user_id, skip=skip, limit=page_size
        )
        return [self._to_response(doc) for doc in docs]

    async def get(self, company_id: UUID, *, firebase_uid: str) -> CompanyResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        doc = await self._repo.get(company_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Company not found.")
        await self._ensure_owner(doc, owner_user_id)
        return self._to_response(doc)

    async def create(
        self, payload: CompanyCreate, *, firebase_uid: str
    ) -> CompanyResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        if await self._repo.count_for_owner(owner_user_id) > 0:
            raise ConflictError(
                "This user already owns a company.",
                code="owner_already_has_company",
            )
        existing = await self._repo.get_by_tax_id(payload.country, payload.tax_id)
        if existing is not None and existing.is_active:
            raise ConflictError(
                "A company with this tax ID already exists.",
                code="tax_id_exists",
            )

        address = None
        if payload.address is not None:
            address = CompanyAddress.model_validate(payload.address.model_dump())

        doc = CompanyDocument(
            owner_user_id=owner_user_id,
            legal_name=payload.legal_name,
            trade_name=payload.trade_name,
            tax_id=payload.tax_id,
            email=payload.email,
            phone=payload.phone,
            legal_representative=payload.legal_representative,
            address=address,
            country=payload.country,
            website=payload.website,
            description=payload.description,
            logo_storage_key=payload.logo_storage_key,
            logo_url=payload.logo_url,
            sector=payload.sector,
        )
        created = await self._repo.create(doc)
        return self._to_response(created)

    async def update(
        self, company_id: UUID, payload: CompanyUpdate, *, firebase_uid: str
    ) -> CompanyResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        doc = await self._repo.get(company_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Company not found.")
        await self._ensure_owner(doc, owner_user_id)

        patch = payload.model_dump(exclude_unset=True)
        if "address" in patch and patch["address"] is not None:
            patch["address"] = CompanyAddress.model_validate(patch["address"]).model_dump()

        updated = await self._repo.update(company_id, patch)
        if updated is None:
            raise NotFoundError("Company not found.")
        return self._to_response(updated)

    async def delete(self, company_id: UUID, *, firebase_uid: str) -> None:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        doc = await self._repo.get(company_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Company not found.")
        await self._ensure_owner(doc, owner_user_id)
        deleted = await self._repo.delete(company_id)
        if not deleted:
            raise NotFoundError("Company not found.")

    async def presign_logo(
        self, payload: LogoPresignRequest, *, firebase_uid: str
    ) -> LogoPresignResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        content_type = payload.content_type.lower()
        if content_type not in _ALLOWED_LOGO_TYPES:
            raise ConflictError(
                "Unsupported image type. Use JPEG, PNG, WebP, GIF or SVG.",
                code="invalid_content_type",
            )

        extension = payload.filename.rsplit(".", 1)[-1].lower() if "." in payload.filename else "bin"
        storage_key = logo_storage_key(owner_user_id, extension)
        expires_in = 900
        expires_at = utcnow() + timedelta(seconds=expires_in)

        upload_url, public_url = await firebase.presign_storage_upload(
            storage_key,
            content_type=content_type,
            expires_in=expires_in,
        )

        return LogoPresignResponse(
            upload_url=upload_url,
            storage_key=storage_key,
            public_url=public_url,
            expires_at=expires_at,
        )

    async def upload_logo(
        self, file: UploadFile, *, firebase_uid: str
    ) -> StorageUploadResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        extension = extension_from_filename(file.filename or "logo.bin")
        storage_key = logo_storage_key(owner_user_id, extension)
        public_url = await upload_image_file(
            file,
            allowed_types=_ALLOWED_LOGO_TYPES,
            storage_key=storage_key,
        )
        return StorageUploadResponse(storage_key=storage_key, public_url=public_url)

    async def upload_document(
        self,
        company_id: UUID,
        kind: str,
        file: UploadFile,
        *,
        firebase_uid: str | None = None,
        as_admin: bool = False,
        mark_approved: bool = True,
    ) -> CompanyResponse:
        field = document_field(kind)
        doc = await self._repo.get(company_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Company not found.")
        if not as_admin:
            if firebase_uid is None:
                raise ForbiddenError("You do not have access to this company.")
            owner_user_id = await self._resolve_user_id(firebase_uid)
            await self._ensure_owner(doc, owner_user_id)
        uploaded = await upload_compliance_file(file, owner_user_id=doc.owner_user_id)
        if as_admin and mark_approved:
            uploaded = uploaded.model_copy(
                update={
                    "status": ComplianceDocumentStatus.APPROVED,
                    "rejection_reason": None,
                    "reviewed_at": utcnow(),
                    "reviewed_by": None,
                }
            )
        updated = await self._repo.update(
            company_id, {field: uploaded.model_dump()}
        )
        if updated is None:
            raise NotFoundError("Company not found.")
        if not as_admin or not mark_approved:
            await self._enqueue_document_review(updated)
        return self._to_response(updated)

    async def _enqueue_document_review(self, company: CompanyDocument) -> None:
        if self._compliance_review is None:
            return
        try:
            await self._compliance_review.enqueue(
                company,
                message=(
                    f"A empresa {company.legal_name} enviou documentos para análise."
                ),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "compliance_review_enqueue_failed", company_id=str(company.id)
            )


__all__ = ["CompaniesService"]
