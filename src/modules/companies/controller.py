"""HTTP controller for ``companies``."""

from __future__ import annotations

from uuid import UUID

from fastapi import UploadFile

from src.modules.companies.schema import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    LogoPresignRequest,
    LogoPresignResponse,
)
from src.modules.companies.service import CompaniesService
from src.shared.dependencies.auth import CurrentUser
from src.shared.schemas.responses import StorageUploadResponse


class CompaniesController:
    def __init__(self, service: CompaniesService) -> None:
        self._service = service

    async def list(
        self, current_user: CurrentUser, page: int, page_size: int
    ) -> list[CompanyResponse]:
        return await self._service.list(
            firebase_uid=current_user.uid, page=page, page_size=page_size
        )

    async def get(self, company_id: UUID, current_user: CurrentUser) -> CompanyResponse:
        return await self._service.get(company_id, firebase_uid=current_user.uid)

    async def create(
        self, payload: CompanyCreate, current_user: CurrentUser
    ) -> CompanyResponse:
        return await self._service.create(payload, firebase_uid=current_user.uid)

    async def update(
        self, company_id: UUID, payload: CompanyUpdate, current_user: CurrentUser
    ) -> CompanyResponse:
        return await self._service.update(
            company_id, payload, firebase_uid=current_user.uid
        )

    async def delete(self, company_id: UUID, current_user: CurrentUser) -> None:
        await self._service.delete(company_id, firebase_uid=current_user.uid)

    async def presign_logo(
        self, payload: LogoPresignRequest, current_user: CurrentUser
    ) -> LogoPresignResponse:
        return await self._service.presign_logo(
            payload, firebase_uid=current_user.uid
        )

    async def upload_logo(
        self, file: UploadFile, current_user: CurrentUser
    ) -> StorageUploadResponse:
        return await self._service.upload_logo(
            file, firebase_uid=current_user.uid
        )

    async def upload_document(
        self,
        company_id: UUID,
        kind: str,
        file: UploadFile,
        current_user: CurrentUser,
    ) -> CompanyResponse:
        return await self._service.upload_document(
            company_id, kind, file, firebase_uid=current_user.uid
        )


__all__ = ["CompaniesController"]
