"""HTTP controller for ``opportunities``."""

from __future__ import annotations

from uuid import UUID

from fastapi import UploadFile

from src.modules.opportunities.schema import (
    OpportunityCreate,
    OpportunityImagePresignRequest,
    OpportunityImagePresignResponse,
    OpportunityListParams,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from src.modules.opportunities.service import OpportunitiesService
from src.shared.dependencies.auth import CurrentUser
from src.shared.schemas.responses import StorageUploadResponse


class OpportunitiesController:
    def __init__(self, service: OpportunitiesService) -> None:
        self._service = service

    async def list(
        self, params: OpportunityListParams, current_user: CurrentUser
    ) -> OpportunityListResponse:
        return await self._service.list(
            params, firebase_uid=current_user.uid
        )

    async def get(
        self, opportunity_id: UUID, current_user: CurrentUser
    ) -> OpportunityResponse:
        return await self._service.get(
            opportunity_id, firebase_uid=current_user.uid
        )

    async def create(
        self, payload: OpportunityCreate, current_user: CurrentUser
    ) -> OpportunityResponse:
        return await self._service.create(
            payload, firebase_uid=current_user.uid
        )

    async def update(
        self,
        opportunity_id: UUID,
        payload: OpportunityUpdate,
        current_user: CurrentUser,
    ) -> OpportunityResponse:
        return await self._service.update(
            opportunity_id, payload, firebase_uid=current_user.uid
        )

    async def delete(
        self, opportunity_id: UUID, current_user: CurrentUser
    ) -> None:
        await self._service.delete(
            opportunity_id, firebase_uid=current_user.uid
        )

    async def presign_image(
        self,
        payload: OpportunityImagePresignRequest,
        current_user: CurrentUser,
    ) -> OpportunityImagePresignResponse:
        return await self._service.presign_image(
            payload, firebase_uid=current_user.uid
        )

    async def upload_image(
        self, file: UploadFile, current_user: CurrentUser
    ) -> StorageUploadResponse:
        return await self._service.upload_image(
            file, firebase_uid=current_user.uid
        )


__all__ = ["OpportunitiesController"]
