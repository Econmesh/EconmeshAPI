"""HTTP controller for ``agreements``."""

from __future__ import annotations

from uuid import UUID

from fastapi import Request, UploadFile

from src.modules.agreements.schema import (
    AgreementCreate,
    AgreementListParams,
    AgreementListResponse,
    AgreementResponse,
    AgreementUpdate,
    CompanySearchResponse,
    DownloadUrlResponse,
    FieldsUpdate,
    ParticipantsUpdate,
    ProgressResponse,
    RejectRequest,
    SignRequest,
    TimelineResponse,
)
from src.modules.agreements.service import AgreementsService
from src.shared.dependencies.auth import CurrentUser


class AgreementsController:
    def __init__(self, service: AgreementsService) -> None:
        self._service = service

    @staticmethod
    def _client_meta(request: Request) -> tuple[str | None, str | None]:
        forwarded = request.headers.get("x-forwarded-for")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else None
        )
        ua = request.headers.get("user-agent")
        return ip, ua

    async def list(
        self, params: AgreementListParams, current_user: CurrentUser
    ) -> AgreementListResponse:
        return await self._service.list(
            params, firebase_uid=current_user.uid, role=current_user.role
        )

    async def get(
        self, agreement_id: UUID, current_user: CurrentUser
    ) -> AgreementResponse:
        return await self._service.get(
            agreement_id, firebase_uid=current_user.uid, role=current_user.role
        )

    async def create(
        self, payload: AgreementCreate, current_user: CurrentUser
    ) -> AgreementResponse:
        return await self._service.create(payload, firebase_uid=current_user.uid)

    async def update(
        self,
        agreement_id: UUID,
        payload: AgreementUpdate,
        current_user: CurrentUser,
    ) -> AgreementResponse:
        return await self._service.update(
            agreement_id, payload, firebase_uid=current_user.uid
        )

    async def cancel(
        self, agreement_id: UUID, current_user: CurrentUser
    ) -> AgreementResponse:
        return await self._service.cancel(
            agreement_id, firebase_uid=current_user.uid
        )

    async def upload(
        self, agreement_id: UUID, file: UploadFile, current_user: CurrentUser
    ) -> AgreementResponse:
        return await self._service.upload_pdf(
            agreement_id, file, firebase_uid=current_user.uid
        )

    async def update_participants(
        self,
        agreement_id: UUID,
        payload: ParticipantsUpdate,
        current_user: CurrentUser,
    ) -> AgreementResponse:
        return await self._service.update_participants(
            agreement_id, payload, firebase_uid=current_user.uid
        )

    async def update_fields(
        self,
        agreement_id: UUID,
        payload: FieldsUpdate,
        current_user: CurrentUser,
    ) -> AgreementResponse:
        return await self._service.update_fields(
            agreement_id, payload, firebase_uid=current_user.uid
        )

    async def send(
        self, agreement_id: UUID, current_user: CurrentUser
    ) -> AgreementResponse:
        return await self._service.send(
            agreement_id, firebase_uid=current_user.uid
        )

    async def view(
        self, agreement_id: UUID, current_user: CurrentUser, request: Request
    ) -> AgreementResponse:
        ip, ua = self._client_meta(request)
        return await self._service.mark_viewed(
            agreement_id,
            firebase_uid=current_user.uid,
            ip=ip,
            user_agent=ua,
        )

    async def sign(
        self,
        agreement_id: UUID,
        payload: SignRequest,
        current_user: CurrentUser,
        request: Request,
    ) -> AgreementResponse:
        ip, ua = self._client_meta(request)
        return await self._service.sign(
            agreement_id,
            payload,
            firebase_uid=current_user.uid,
            ip=ip,
            user_agent=ua,
        )

    async def reject(
        self,
        agreement_id: UUID,
        payload: RejectRequest,
        current_user: CurrentUser,
        request: Request,
    ) -> AgreementResponse:
        ip, ua = self._client_meta(request)
        return await self._service.reject(
            agreement_id,
            payload,
            firebase_uid=current_user.uid,
            ip=ip,
            user_agent=ua,
        )

    async def timeline(
        self, agreement_id: UUID, current_user: CurrentUser
    ) -> TimelineResponse:
        return await self._service.timeline(
            agreement_id, firebase_uid=current_user.uid, role=current_user.role
        )

    async def progress(
        self, agreement_id: UUID, current_user: CurrentUser
    ) -> ProgressResponse:
        return await self._service.progress(
            agreement_id, firebase_uid=current_user.uid, role=current_user.role
        )

    async def download(
        self,
        agreement_id: UUID,
        artifact: str,
        current_user: CurrentUser,
        request: Request,
    ) -> DownloadUrlResponse:
        ip, ua = self._client_meta(request)
        url = await self._service.download_url(
            agreement_id,
            artifact,
            firebase_uid=current_user.uid,
            role=current_user.role,
            ip=ip,
            user_agent=ua,
        )
        return DownloadUrlResponse(url=url, artifact=artifact)

    async def download_file(
        self,
        agreement_id: UUID,
        artifact: str,
        current_user: CurrentUser,
    ) -> tuple[bytes, str]:
        return await self._service.download_file_bytes(
            agreement_id,
            artifact,
            firebase_uid=current_user.uid,
            role=current_user.role,
        )

    async def search_companies(
        self, q: str, current_user: CurrentUser
    ) -> CompanySearchResponse:
        return await self._service.search_companies(
            q, firebase_uid=current_user.uid
        )

    async def eligibility(
        self, current_user: CurrentUser, company_id: UUID | None
    ) -> dict:
        return await self._service.check_eligibility(
            firebase_uid=current_user.uid, company_id=company_id
        )


__all__ = ["AgreementsController"]
