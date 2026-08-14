"""HTTP controller for the ``admin`` module."""

from __future__ import annotations

from uuid import UUID

from fastapi import UploadFile

from src.modules.admin.schema import (
    AdminCompanyCreate,
    AdminCompanyListResponse,
    AdminRegisterRequest,
    AdminUserListItem,
    AdminUserListParams,
    AdminUserListResponse,
    AdminUserUpdate,
)
from src.modules.admin.service import AdminService
from src.modules.auth.schema import MeResponse, RegisterResponse
from src.modules.companies.schema import CompanyResponse, CompanyUpdate
from src.modules.users.schema import UserProfileResponse
from src.modules.opportunities.schema import (
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
)


class AdminController:
    def __init__(self, service: AdminService) -> None:
        self._service = service

    async def list_users(self, params: AdminUserListParams) -> AdminUserListResponse:
        return await self._service.list_users(params)

    async def get_user(self, user_id: UUID) -> AdminUserListItem:
        return await self._service.get_user(user_id)

    async def create_user(self, payload: AdminRegisterRequest) -> RegisterResponse:
        return await self._service.create_user(payload)

    async def update_user(self, user_id: UUID, payload: AdminUserUpdate) -> MeResponse:
        return await self._service.update_user(user_id, payload)

    async def get_user_profile(self, user_id: UUID) -> UserProfileResponse:
        return await self._service.get_user_profile(user_id)

    async def delete_user(self, user_id: UUID, *, actor_firebase_uid: str) -> None:
        await self._service.delete_user(user_id, actor_firebase_uid=actor_firebase_uid)

    async def list_companies(self, *, page: int, page_size: int) -> AdminCompanyListResponse:
        return await self._service.list_companies(page=page, page_size=page_size)

    async def get_company(self, company_id: UUID) -> CompanyResponse:
        return await self._service.get_company(company_id)

    async def create_company(self, payload: AdminCompanyCreate) -> CompanyResponse:
        return await self._service.create_company(payload)

    async def update_company(
        self, company_id: UUID, payload: CompanyUpdate
    ) -> CompanyResponse:
        return await self._service.update_company(company_id, payload)

    async def delete_company(self, company_id: UUID) -> None:
        await self._service.delete_company(company_id)

    async def upload_company_document(
        self,
        company_id: UUID,
        kind: str,
        file: UploadFile,
        *,
        approve: bool = True,
    ) -> CompanyResponse:
        return await self._service.upload_company_document(
            company_id, kind, file, approve=approve
        )

    async def approve_company_document(
        self, company_id: UUID, kind: str, *, firebase_uid: str
    ) -> CompanyResponse:
        return await self._service.approve_company_document(
            company_id, kind, firebase_uid=firebase_uid
        )

    async def reject_company_document(
        self, company_id: UUID, kind: str, reason: str, *, firebase_uid: str
    ) -> CompanyResponse:
        return await self._service.reject_company_document(
            company_id, kind, reason, firebase_uid=firebase_uid
        )

    async def list_opportunities(
        self, params: OpportunityListParams
    ) -> OpportunityListResponse:
        return await self._service.list_opportunities(params)

    async def get_opportunity(self, opportunity_id: UUID) -> OpportunityResponse:
        return await self._service.get_opportunity(opportunity_id)

    async def update_opportunity(
        self, opportunity_id: UUID, payload: OpportunityUpdate
    ) -> OpportunityResponse:
        return await self._service.update_opportunity(opportunity_id, payload)

    async def delete_opportunity(self, opportunity_id: UUID) -> None:
        await self._service.delete_opportunity(opportunity_id)


__all__ = ["AdminController"]
