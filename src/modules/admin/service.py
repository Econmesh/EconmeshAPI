"""Business rules for cross-tenant admin operations."""

from __future__ import annotations

from uuid import UUID

from src.core.exceptions import ConflictError, NotFoundError
from src.core.firebase import firebase
from src.modules.admin.schema import (
    AdminCompanyCreate,
    AdminCompanyListResponse,
    AdminRegisterRequest,
    AdminUserListItem,
    AdminUserListParams,
    AdminUserListResponse,
    AdminUserUpdate,
)
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schema import MeResponse, RegisterResponse
from src.modules.auth.service import AuthService
from src.modules.companies.model import CompanyAddress, CompanyDocument
from src.modules.companies.repository import CompaniesRepository
from src.modules.companies.schema import CompanyResponse, CompanyUpdate
from src.modules.companies.service import CompaniesService
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.opportunities.schema import (
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from src.modules.opportunities.service import OpportunitiesService
from src.shared.constants.roles import Role


class AdminService:
    def __init__(
        self,
        auth_repository: AuthRepository,
        auth_service: AuthService,
        companies_repository: CompaniesRepository,
        companies_service: CompaniesService,
        opportunities_repository: OpportunitiesRepository,
        opportunities_service: OpportunitiesService,
    ) -> None:
        self._auth_repo = auth_repository
        self._auth_service = auth_service
        self._companies_repo = companies_repository
        self._companies_service = companies_service
        self._opportunities_repo = opportunities_repository
        self._opportunities_service = opportunities_service

    @staticmethod
    def _user_to_list_item(user: UserDocument) -> AdminUserListItem:
        return AdminUserListItem(
            id=user.id,
            firebase_uid=user.firebase_uid,
            email=user.email,
            name=user.name,
            phone=user.phone,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            email_verified=user.email_verified,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )

    @staticmethod
    def _user_to_me(user: UserDocument) -> MeResponse:
        return MeResponse(
            id=user.id,
            firebase_uid=user.firebase_uid,
            email=user.email,
            name=user.name,
            phone=user.phone,
            picture=user.picture,
            email_verified=user.email_verified,
            is_verified=user.is_verified,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )

    async def list_users(self, params: AdminUserListParams) -> AdminUserListResponse:
        skip = (params.page - 1) * params.page_size
        docs = await self._auth_repo.list_users(
            skip=skip,
            limit=params.page_size,
            role=params.role,
            is_active=params.is_active,
            email=params.email,
        )
        total = await self._auth_repo.count_users(
            role=params.role,
            is_active=params.is_active,
            email=params.email,
        )
        has_more = params.page * params.page_size < total
        return AdminUserListResponse(
            items=[self._user_to_list_item(doc) for doc in docs],
            total=total,
            page=params.page,
            page_size=params.page_size,
            has_more=has_more,
        )

    async def get_user(self, user_id: UUID) -> AdminUserListItem:
        user = await self._auth_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return self._user_to_list_item(user)

    async def create_user(self, payload: AdminRegisterRequest) -> RegisterResponse:
        return await self._auth_service.register_by_admin(payload)

    async def update_user(self, user_id: UUID, payload: AdminUserUpdate) -> MeResponse:
        user = await self._auth_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")

        patch = payload.model_dump(exclude_unset=True)
        role = patch.pop("role", None)
        is_active = patch.pop("is_active", None)

        if patch:
            updated = await self._auth_repo.update_profile(user_id, patch)
            if updated is None:
                raise NotFoundError("User not found.", code="user_not_found")
            user = updated

        if role is not None:
            role_enum = Role(role)
            await self._auth_repo.set_role(user_id, role=role_enum)
            await firebase.set_custom_user_claims(
                user.firebase_uid, {"role": role_enum.value}
            )
            user = await self._auth_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError("User not found.", code="user_not_found")

        if is_active is not None:
            await self._auth_repo.set_active(user_id, is_active=is_active)
            await firebase.update_user(user.firebase_uid, disabled=not is_active)
            user = await self._auth_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError("User not found.", code="user_not_found")

        return self._user_to_me(user)

    async def list_companies(self, *, page: int, page_size: int) -> AdminCompanyListResponse:
        skip = (page - 1) * page_size
        docs = await self._companies_repo.list_all(skip=skip, limit=page_size)
        total = await self._companies_repo.count_all()
        has_more = page * page_size < total
        return AdminCompanyListResponse(
            items=[self._companies_service._to_response(doc) for doc in docs],
            total=total,
            page=page,
            page_size=page_size,
            has_more=has_more,
        )

    async def get_company(self, company_id: UUID) -> CompanyResponse:
        doc = await self._companies_repo.get(company_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Company not found.")
        return self._companies_service._to_response(doc)

    async def create_company(self, payload: AdminCompanyCreate) -> CompanyResponse:
        owner = await self._auth_repo.get_by_id(payload.owner_user_id)
        if owner is None:
            raise NotFoundError("Owner user not found.", code="user_not_found")

        existing = await self._companies_repo.get_by_tax_id(payload.country, payload.tax_id)
        if existing is not None and existing.is_active:
            raise ConflictError(
                "A company with this tax ID already exists.",
                code="tax_id_exists",
            )

        address = None
        if payload.address is not None:
            address = CompanyAddress.model_validate(payload.address.model_dump())

        doc = CompanyDocument(
            owner_user_id=payload.owner_user_id,
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
        created = await self._companies_repo.create(doc)
        return self._companies_service._to_response(created)

    async def update_company(
        self, company_id: UUID, payload: CompanyUpdate
    ) -> CompanyResponse:
        doc = await self._companies_repo.get(company_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Company not found.")

        patch = payload.model_dump(exclude_unset=True)
        if "address" in patch and patch["address"] is not None:
            patch["address"] = CompanyAddress.model_validate(patch["address"]).model_dump()

        updated = await self._companies_repo.update(company_id, patch)
        if updated is None:
            raise NotFoundError("Company not found.")
        return self._companies_service._to_response(updated)

    async def delete_company(self, company_id: UUID) -> None:
        doc = await self._companies_repo.get(company_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Company not found.")
        deleted = await self._companies_repo.delete(company_id)
        if not deleted:
            raise NotFoundError("Company not found.")

    async def list_opportunities(
        self, params: OpportunityListParams
    ) -> OpportunityListResponse:
        docs = await self._opportunities_repo.list_filtered(params)
        total = await self._opportunities_repo.count_filtered(params)
        has_more = params.page * params.page_size < total
        return OpportunityListResponse(
            items=[
                self._opportunities_service._to_response(doc) for doc in docs
            ],
            total=total,
            page=params.page,
            page_size=params.page_size,
            has_more=has_more,
        )

    async def get_opportunity(self, opportunity_id: UUID) -> OpportunityResponse:
        doc = await self._opportunities_repo.get(opportunity_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Opportunity not found.")
        return self._opportunities_service._to_response(doc)

    async def update_opportunity(
        self, opportunity_id: UUID, payload: OpportunityUpdate
    ) -> OpportunityResponse:
        doc = await self._opportunities_repo.get(opportunity_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Opportunity not found.")

        patch = payload.model_dump(exclude_unset=True)
        if "images" in patch and patch["images"] is not None:
            from src.modules.opportunities.schema import OpportunityImageInput

            images_input = [
                OpportunityImageInput.model_validate(img) for img in patch["images"]
            ]
            patch["images"] = [
                img.model_dump()
                for img in self._opportunities_service._normalize_images(images_input)
            ]

        updated = await self._opportunities_repo.update(opportunity_id, patch)
        if updated is None:
            raise NotFoundError("Opportunity not found.")
        return self._opportunities_service._to_response(updated)

    async def delete_opportunity(self, opportunity_id: UUID) -> None:
        doc = await self._opportunities_repo.get(opportunity_id)
        if doc is None or not doc.is_active:
            raise NotFoundError("Opportunity not found.")
        deleted = await self._opportunities_repo.delete(opportunity_id)
        if not deleted:
            raise NotFoundError("Opportunity not found.")


__all__ = ["AdminService"]
