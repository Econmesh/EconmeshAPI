"""Routes for ``agreements``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response

from src.infrastructure.email import email_sender
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.modules.agreements.controller import AgreementsController
from src.modules.agreements.notification_service import AgreementNotificationService
from src.modules.agreements.repository import AgreementEventsRepository, AgreementsRepository
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
from src.modules.auth.repository import AuthRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.conversations.repository import ConversationMessagesRepository
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.users.repository import UsersRepository
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/agreements", tags=["agreements"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis: Annotated["Redis", Depends(get_redis)],
) -> AgreementsController:
    repo = AgreementsRepository(db)
    events_repo = AgreementEventsRepository(db)
    auth_repo = AuthRepository(db)
    companies_repo = CompaniesRepository(db)
    users_repo = UsersRepository(db)
    notifications = AgreementNotificationService(
        auth_repo=auth_repo,
        user_notifications_repo=UserNotificationsRepository(db),
        email_sender=email_sender,
        notification_realtime=NotificationRealtimePublisher(redis),
    )
    service = AgreementsService(
        repo,
        events_repo,
        auth_repo,
        companies_repo,
        users_repo,
        notifications=notifications,
        messages_repository=ConversationMessagesRepository(db),
        opportunities_repository=OpportunitiesRepository(db),
    )
    return AgreementsController(service)


ControllerDep = Annotated[AgreementsController, Depends(_build_controller)]


@router.get(
    "",
    response_model=AgreementListResponse,
    summary="List agreements visible to the current user.",
)
async def list_agreements(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    params: Annotated[AgreementListParams, Depends(AgreementListParams.as_query)],
) -> AgreementListResponse:
    return await controller.list(params, current_user)


@router.post(
    "",
    response_model=AgreementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft agreement.",
)
async def create_agreement(
    payload: AgreementCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.create(payload, current_user)


@router.get(
    "/companies/search",
    response_model=CompanySearchResponse,
    summary="Search companies to add as agreement participants.",
)
async def search_companies(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    q: str = Query("", max_length=200),
) -> CompanySearchResponse:
    return await controller.search_companies(q, current_user)


@router.get(
    "/eligibility",
    summary="Check if the user/company profile is complete for agreements.",
)
async def check_eligibility(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    company_id: UUID | None = Query(None),
) -> dict:
    return await controller.eligibility(current_user, company_id)


@router.get(
    "/{agreement_id}",
    response_model=AgreementResponse,
    summary="Get agreement detail.",
)
async def get_agreement(
    agreement_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.get(agreement_id, current_user)


@router.patch(
    "/{agreement_id}",
    response_model=AgreementResponse,
    summary="Update draft agreement metadata.",
)
async def update_agreement(
    agreement_id: UUID,
    payload: AgreementUpdate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.update(agreement_id, payload, current_user)


@router.delete(
    "/{agreement_id}",
    response_model=AgreementResponse,
    summary="Cancel an agreement.",
)
async def cancel_agreement(
    agreement_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.cancel(agreement_id, current_user)


@router.post(
    "/{agreement_id}/upload",
    response_model=AgreementResponse,
    summary="Upload the agreement PDF.",
)
async def upload_agreement_pdf(
    agreement_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
) -> AgreementResponse:
    return await controller.upload(agreement_id, file, current_user)


@router.put(
    "/{agreement_id}/participants",
    response_model=AgreementResponse,
    summary="Replace agreement participants.",
)
async def update_participants(
    agreement_id: UUID,
    payload: ParticipantsUpdate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.update_participants(agreement_id, payload, current_user)


@router.put(
    "/{agreement_id}/fields",
    response_model=AgreementResponse,
    summary="Replace signature field positions.",
)
async def update_fields(
    agreement_id: UUID,
    payload: FieldsUpdate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.update_fields(agreement_id, payload, current_user)


@router.post(
    "/{agreement_id}/send",
    response_model=AgreementResponse,
    summary="Send the agreement for signatures.",
)
async def send_agreement(
    agreement_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.send(agreement_id, current_user)


@router.post(
    "/{agreement_id}/view",
    response_model=AgreementResponse,
    summary="Record that the current user viewed the agreement.",
)
async def view_agreement(
    agreement_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
    request: Request,
) -> AgreementResponse:
    return await controller.view(agreement_id, current_user, request)


@router.post(
    "/{agreement_id}/sign",
    response_model=AgreementResponse,
    summary="Complete the current user's signing step.",
)
async def sign_agreement(
    agreement_id: UUID,
    payload: SignRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
    request: Request,
) -> AgreementResponse:
    return await controller.sign(agreement_id, payload, current_user, request)


@router.post(
    "/{agreement_id}/reject",
    response_model=AgreementResponse,
    summary="Reject the agreement.",
)
async def reject_agreement(
    agreement_id: UUID,
    payload: RejectRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
    request: Request,
) -> AgreementResponse:
    return await controller.reject(agreement_id, payload, current_user, request)


@router.get(
    "/{agreement_id}/timeline",
    response_model=TimelineResponse,
    summary="Agreement audit timeline.",
)
async def agreement_timeline(
    agreement_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> TimelineResponse:
    return await controller.timeline(agreement_id, current_user)


@router.get(
    "/{agreement_id}/progress",
    response_model=ProgressResponse,
    summary="Agreement progress panel.",
)
async def agreement_progress(
    agreement_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ProgressResponse:
    return await controller.progress(agreement_id, current_user)


@router.get(
    "/{agreement_id}/download/{artifact}",
    response_model=DownloadUrlResponse,
    summary="Get download URL for an agreement artifact.",
)
async def download_agreement_artifact(
    agreement_id: UUID,
    artifact: str,
    controller: ControllerDep,
    current_user: CurrentUserDep,
    request: Request,
) -> DownloadUrlResponse:
    return await controller.download(agreement_id, artifact, current_user, request)


@router.get(
    "/{agreement_id}/file/{artifact}",
    summary="Stream agreement artifact bytes (PDF proxy).",
    response_class=Response,
)
async def stream_agreement_artifact(
    agreement_id: UUID,
    artifact: str,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> Response:
    data, filename = await controller.download_file(
        agreement_id, artifact, current_user
    )
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )


__all__ = ["router"]
