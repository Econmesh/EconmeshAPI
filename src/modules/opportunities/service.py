"""Business rules for ``opportunities``."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import UploadFile

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.firebase import firebase
from src.modules.auth.repository import AuthRepository
from src.modules.billing.service import BillingService
from src.modules.companies.repository import CompaniesRepository
from src.modules.opportunities.matching_service import MatchingService
from src.modules.opportunities.model import OfferDemand, OpportunityDocument, OpportunityImage
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.opportunities.schema import (
    OpportunityCreate,
    OpportunityImageInput,
    OpportunityImagePresignRequest,
    OpportunityImagePresignResponse,
    OpportunityImageResponse,
    OpportunityListItem,
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityPreviewResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from src.shared.schemas.responses import StorageUploadResponse
from src.shared.utils.image_upload import extension_from_filename, upload_image_file
from src.shared.utils.storage_keys import image_storage_key
from src.shared.utils.time import utcnow

_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


class OpportunitiesService:
    def __init__(
        self,
        repository: OpportunitiesRepository,
        auth_repository: AuthRepository,
        companies_repository: CompaniesRepository,
        billing_service: BillingService,
    ) -> None:
        self._repo = repository
        self._auth_repo = auth_repository
        self._companies_repo = companies_repository
        self._billing = billing_service

    async def _resolve_user_id(self, firebase_uid: str) -> UUID:
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user.id

    async def _ensure_owner(
        self, doc: OpportunityDocument, owner_user_id: UUID
    ) -> None:
        if doc.owner_user_id != owner_user_id:
            raise ForbiddenError("You do not have access to this opportunity.")

    @staticmethod
    def _normalize_images(
        images: list[OpportunityImageInput],
    ) -> list[OpportunityImage]:
        if not images:
            return []

        normalized: list[OpportunityImage] = []
        has_primary = any(img.is_primary for img in images)
        for index, img in enumerate(images):
            normalized.append(
                OpportunityImage(
                    storage_key=img.storage_key,
                    url=img.url,
                    is_primary=img.is_primary if has_primary else index == 0,
                    sort_order=img.sort_order if img.sort_order else index,
                )
            )
        return normalized

    async def _user_has_access(self, firebase_uid: str, *, is_admin: bool) -> bool:
        if is_admin:
            return True
        me = await self._billing.get_me(firebase_uid=firebase_uid, is_admin=False)
        return me.has_access

    def _to_preview(self, doc: OpportunityDocument) -> OpportunityPreviewResponse:
        return OpportunityPreviewResponse(
            id=doc.id,
            title=doc.title,
            images=[
                OpportunityImageResponse.model_validate(img.model_dump())
                for img in doc.images
            ],
            opportunity_type=doc.opportunity_type,
            offer_demand=doc.offer_demand,
            category=doc.category,
        )

    def _to_response(self, doc: OpportunityDocument) -> OpportunityResponse:
        return OpportunityResponse(
            id=doc.id,
            company_id=doc.company_id,
            company_name=doc.company_name,
            owner_user_id=doc.owner_user_id,
            title=doc.title,
            description=doc.description,
            opportunity_type=doc.opportunity_type,
            offer_demand=doc.offer_demand,
            category=doc.category,
            technical_detail=doc.technical_detail,
            purity_percent=doc.purity_percent,
            physical_state=doc.physical_state,
            periodicity=doc.periodicity,
            quantity=doc.quantity,
            unit=doc.unit,
            price=doc.price,
            price_negotiable=doc.price_negotiable,
            city=doc.city,
            state=doc.state,
            latitude=doc.latitude,
            longitude=doc.longitude,
            images=[
                OpportunityImageResponse.model_validate(img.model_dump())
                for img in doc.images
            ],
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def _resolve_owned_company(
        self, company_id: UUID, owner_user_id: UUID
    ) -> tuple[str, UUID]:
        company = await self._companies_repo.get(company_id)
        if company is None or not company.is_active:
            raise NotFoundError("Company not found.")
        if company.owner_user_id != owner_user_id:
            raise ForbiddenError("You do not have access to this company.")
        company_name = company.trade_name or company.legal_name
        return company_name, company.owner_user_id

    async def list(
        self,
        params: OpportunityListParams,
        *,
        firebase_uid: str,
        is_admin: bool = False,
    ) -> OpportunityListResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        docs = await self._repo.list_filtered(params)
        total = await self._repo.count_filtered(params)
        has_more = params.page * params.page_size < total

        has_access = await self._user_has_access(firebase_uid, is_admin=is_admin)
        if not has_access:
            return OpportunityListResponse(
                items=[self._to_preview(doc) for doc in docs],
                total=total,
                page=params.page,
                page_size=params.page_size,
                has_more=has_more,
                has_demands=False,
                is_preview=True,
            )

        demands = await self._repo.list_demands_for_owner(owner_user_id)
        has_demands = len(demands) > 0
        demand_responses = {
            str(demand.id): self._to_response(demand) for demand in demands
        }

        items: list[OpportunityListItem] = []
        for doc in docs:
            response = self._to_response(doc)
            if (
                has_demands
                and doc.offer_demand == OfferDemand.GERADOR
                and doc.owner_user_id != owner_user_id
            ):
                matching = MatchingService.find_best_match(
                    doc,
                    demands,
                    demand_responses=demand_responses,
                )
                if matching is not None:
                    response = response.model_copy(update={"matching": matching})
            items.append(response)

        return OpportunityListResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            has_more=has_more,
            has_demands=has_demands,
            is_preview=False,
        )

    async def get(
        self, opportunity_id: UUID, *, firebase_uid: str
    ) -> OpportunityResponse:
        await self._resolve_user_id(firebase_uid)
        doc = await self._repo.get(opportunity_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Opportunity not found.")
        return self._to_response(doc)

    async def create(
        self, payload: OpportunityCreate, *, firebase_uid: str
    ) -> OpportunityResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        company_name, _ = await self._resolve_owned_company(
            payload.company_id, owner_user_id
        )

        doc = OpportunityDocument(
            company_id=payload.company_id,
            company_name=company_name,
            owner_user_id=owner_user_id,
            title=payload.title,
            description=payload.description,
            opportunity_type=payload.opportunity_type,
            offer_demand=payload.offer_demand,
            category=payload.category,
            technical_detail=payload.technical_detail,
            purity_percent=payload.purity_percent,
            physical_state=payload.physical_state,
            periodicity=payload.periodicity,
            quantity=payload.quantity,
            unit=payload.unit,
            price=payload.price,
            price_negotiable=payload.price_negotiable,
            city=payload.city,
            state=payload.state,
            latitude=payload.latitude,
            longitude=payload.longitude,
            images=self._normalize_images(payload.images),
        )
        created = await self._repo.create(doc)
        return self._to_response(created)

    async def update(
        self, opportunity_id: UUID, payload: OpportunityUpdate, *, firebase_uid: str
    ) -> OpportunityResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        doc = await self._repo.get(opportunity_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Opportunity not found.")
        await self._ensure_owner(doc, owner_user_id)

        patch = payload.model_dump(exclude_unset=True)
        if "images" in patch and patch["images"] is not None:
            images_input = [
                OpportunityImageInput.model_validate(img) for img in patch["images"]
            ]
            patch["images"] = [
                img.model_dump()
                for img in self._normalize_images(images_input)
            ]

        updated = await self._repo.update(opportunity_id, patch)
        if updated is None:
            raise NotFoundError("Opportunity not found.")
        return self._to_response(updated)

    async def delete(self, opportunity_id: UUID, *, firebase_uid: str) -> None:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        doc = await self._repo.get(opportunity_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Opportunity not found.")
        await self._ensure_owner(doc, owner_user_id)
        deleted = await self._repo.delete(opportunity_id)
        if not deleted:
            raise NotFoundError("Opportunity not found.")

    async def presign_image(
        self, payload: OpportunityImagePresignRequest, *, firebase_uid: str
    ) -> OpportunityImagePresignResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        content_type = payload.content_type.lower()
        if content_type not in _ALLOWED_IMAGE_TYPES:
            raise ConflictError(
                "Unsupported image type. Use JPEG, PNG, WebP or GIF.",
                code="invalid_content_type",
            )

        extension = (
            payload.filename.rsplit(".", 1)[-1].lower()
            if "." in payload.filename
            else "bin"
        )
        storage_key = image_storage_key(owner_user_id, extension)
        expires_in = 900
        expires_at = utcnow() + timedelta(seconds=expires_in)

        upload_url, public_url = await firebase.presign_storage_upload(
            storage_key,
            content_type=content_type,
            expires_in=expires_in,
        )

        return OpportunityImagePresignResponse(
            upload_url=upload_url,
            storage_key=storage_key,
            public_url=public_url,
            expires_at=expires_at,
        )

    async def upload_image(
        self, file: UploadFile, *, firebase_uid: str
    ) -> StorageUploadResponse:
        owner_user_id = await self._resolve_user_id(firebase_uid)
        extension = extension_from_filename(file.filename or "image.bin")
        storage_key = image_storage_key(owner_user_id, extension)
        public_url = await upload_image_file(
            file,
            allowed_types=_ALLOWED_IMAGE_TYPES,
            storage_key=storage_key,
        )
        return StorageUploadResponse(storage_key=storage_key, public_url=public_url)


__all__ = ["OpportunitiesService"]
