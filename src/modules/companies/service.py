"""Business rules for ``companies``."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.firebase import firebase
from src.modules.auth.repository import AuthRepository
from src.modules.companies.model import CompanyAddress, CompanyDocument
from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.schema import (
    CompanyAddressResponse,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    LogoPresignRequest,
    LogoPresignResponse,
)
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

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
    ) -> None:
        self._repo = repository
        self._auth_repo = auth_repository

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
        return CompanyResponse(
            id=doc.id,
            owner_user_id=doc.owner_user_id,
            legal_name=doc.legal_name,
            trade_name=doc.trade_name,
            tax_id=doc.tax_id,
            email=doc.email,
            phone=doc.phone,
            address=address,
            country=doc.country,
            website=doc.website,
            description=doc.description,
            logo_storage_key=doc.logo_storage_key,
            logo_url=doc.logo_url,
            sector=doc.sector,
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
        storage_key = f"companies/{owner_user_id}/{new_uuid()}.{extension}"
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


__all__ = ["CompaniesService"]
