"""Cross-tenant admin routes — all require ``role=admin``."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from src.modules.admin.controller import AdminController
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
from src.modules.agreements.controller import AgreementsController
from src.modules.agreements.notification_service import AgreementNotificationService
from src.modules.agreements.repository import AgreementEventsRepository, AgreementsRepository
from src.modules.agreements.schema import (
    AgreementListParams,
    AgreementListResponse,
    AgreementResponse,
    DownloadUrlResponse,
    ProgressResponse,
    TimelineResponse,
)
from src.modules.agreements.service import AgreementsService
from src.modules.auth.repository import AuthRepository, EmailVerificationRepository
from src.modules.auth.schema import MeResponse, RegisterResponse
from src.modules.auth.service import AuthService
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
from src.modules.notifications.deps import (
    build_admin_notification_campaigns_controller,
    build_admin_notification_groups_controller,
)
from src.modules.notifications.controller import (
    AdminNotificationCampaignsController,
    AdminNotificationGroupsController,
)
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.notifications.schema import (
    NotificationCampaignCreate,
    NotificationCampaignListResponse,
    NotificationCampaignResponse,
    NotificationGroupCreate,
    NotificationGroupListResponse,
    NotificationGroupResponse,
    NotificationGroupUpdate,
)
from src.modules.blog.controller import AdminBlogController
from src.modules.blog.deps import build_admin_blog_controller
from src.modules.blog.schema import (
    BlogAdminListParams,
    BlogPostCreate,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPostUpdate,
)
from src.modules.support.controller import AdminSupportController
from src.modules.support.deps import build_admin_support_controller, build_support_service
from src.modules.support.schema import (
    AdminSupportTicketListParams,
    SupportInternalNoteCreate,
    SupportMessageCreate,
    SupportMessageListResponse,
    SupportMessageResponse,
    SupportTicketAssign,
    SupportTicketDetailResponse,
    SupportTicketListResponse,
    SupportTicketResponse,
)
from src.modules.users.repository import UsersRepository
from src.infrastructure.email import email_sender
from src.infrastructure.realtime.presence import PresenceService
from src.infrastructure.realtime.redis_pubsub import NotificationRealtimePublisher
from src.infrastructure.realtime.support_pubsub import (
    subscribe_support_admin,
    subscribe_support_ticket,
)
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.constants.roles import Role
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_role
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.pagination import PaginationParams
from src.shared.schemas.responses import MessageResponse, StorageUploadResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> AdminController:
    auth_repo = AuthRepository(db)
    auth_service = AuthService(
        repository=auth_repo,
        redis_client=redis_client,
        verification_repository=EmailVerificationRepository(db),
    )
    companies_repo = CompaniesRepository(db)
    companies_service = CompaniesService(companies_repo, auth_repo)
    opportunities_repo = OpportunitiesRepository(db)
    opportunities_service = OpportunitiesService(
        opportunities_repo, auth_repo, companies_repo
    )
    service = AdminService(
        auth_repository=auth_repo,
        auth_service=auth_service,
        companies_repository=companies_repo,
        companies_service=companies_service,
        opportunities_repository=opportunities_repo,
        opportunities_service=opportunities_service,
    )
    return AdminController(service)


ControllerDep = Annotated[AdminController, Depends(_build_controller)]


def _build_agreements_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> AgreementsController:
    auth_repo = AuthRepository(db)
    notifications = AgreementNotificationService(
        auth_repo=auth_repo,
        user_notifications_repo=UserNotificationsRepository(db),
        email_sender=email_sender,
        notification_realtime=NotificationRealtimePublisher(redis_client),
    )
    service = AgreementsService(
        AgreementsRepository(db),
        AgreementEventsRepository(db),
        auth_repo,
        CompaniesRepository(db),
        UsersRepository(db),
        notifications=notifications,
    )
    return AgreementsController(service)


AgreementsControllerDep = Annotated[
    AgreementsController, Depends(_build_agreements_controller)
]


def _user_list_params(
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
    role: Role | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    email: str | None = Query(default=None, max_length=254),
) -> AdminUserListParams:
    return AdminUserListParams(
        page=pagination.page,
        page_size=pagination.page_size,
        role=role,
        is_active=is_active,
        email=email,
    )


UserListParamsDep = Annotated[AdminUserListParams, Depends(_user_list_params)]


# --------------------------------------------------------------------- users
@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List all users.",
)
async def list_users(
    controller: ControllerDep, params: UserListParamsDep
) -> AdminUserListResponse:
    return await controller.list_users(params)


@router.get(
    "/users/{user_id}",
    response_model=AdminUserListItem,
    summary="Get a user by ID.",
)
async def get_user(controller: ControllerDep, user_id: UUID) -> AdminUserListItem:
    return await controller.get_user(user_id)


@router.post(
    "/users",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user with an arbitrary role.",
)
async def create_user(
    payload: AdminRegisterRequest, controller: ControllerDep
) -> RegisterResponse:
    return await controller.create_user(payload)


@router.patch(
    "/users/{user_id}",
    response_model=MeResponse,
    summary="Update a user (role, status, profile).",
)
async def update_user(
    user_id: UUID, payload: AdminUserUpdate, controller: ControllerDep
) -> MeResponse:
    return await controller.update_user(user_id, payload)


# ----------------------------------------------------------------- companies
@router.get(
    "/companies",
    response_model=AdminCompanyListResponse,
    summary="List all companies.",
)
async def list_companies(
    controller: ControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> AdminCompanyListResponse:
    return await controller.list_companies(
        page=pagination.page, page_size=pagination.page_size
    )


@router.get(
    "/companies/{company_id}",
    response_model=CompanyResponse,
    summary="Get a company by ID.",
)
async def get_company(
    controller: ControllerDep, company_id: UUID
) -> CompanyResponse:
    return await controller.get_company(company_id)


@router.post(
    "/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company for a specific user.",
)
async def create_company(
    payload: AdminCompanyCreate, controller: ControllerDep
) -> CompanyResponse:
    return await controller.create_company(payload)


@router.patch(
    "/companies/{company_id}",
    response_model=CompanyResponse,
    summary="Update a company.",
)
async def update_company(
    company_id: UUID, payload: CompanyUpdate, controller: ControllerDep
) -> CompanyResponse:
    return await controller.update_company(company_id, payload)


@router.delete(
    "/companies/{company_id}",
    response_model=MessageResponse,
    summary="Soft-delete a company.",
)
async def delete_company(
    controller: ControllerDep, company_id: UUID
) -> MessageResponse:
    await controller.delete_company(company_id)
    return MessageResponse(message="Company deleted successfully.")


# ------------------------------------------------------------- opportunities
@router.get(
    "/opportunities",
    response_model=OpportunityListResponse,
    summary="List all opportunities.",
)
async def list_opportunities(
    controller: ControllerDep,
    params: Annotated[OpportunityListParams, Depends(OpportunityListParams.as_query)],
) -> OpportunityListResponse:
    return await controller.list_opportunities(params)


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Get an opportunity by ID.",
)
async def get_opportunity(
    controller: ControllerDep, opportunity_id: UUID
) -> OpportunityResponse:
    return await controller.get_opportunity(opportunity_id)


@router.patch(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Update an opportunity.",
)
async def update_opportunity(
    opportunity_id: UUID,
    payload: OpportunityUpdate,
    controller: ControllerDep,
) -> OpportunityResponse:
    return await controller.update_opportunity(opportunity_id, payload)


@router.delete(
    "/opportunities/{opportunity_id}",
    response_model=MessageResponse,
    summary="Soft-delete an opportunity.",
)
async def delete_opportunity(
    controller: ControllerDep, opportunity_id: UUID
) -> MessageResponse:
    await controller.delete_opportunity(opportunity_id)
    return MessageResponse(message="Opportunity deleted successfully.")


# --------------------------------------------------------------- agreements
@router.get(
    "/agreements",
    response_model=AgreementListResponse,
    summary="List all agreements (platform admin).",
)
async def admin_list_agreements(
    controller: AgreementsControllerDep,
    current_user: CurrentUserDep,
    params: Annotated[AgreementListParams, Depends(AgreementListParams.as_query)],
) -> AgreementListResponse:
    return await controller.list(params, current_user)


@router.get(
    "/agreements/{agreement_id}",
    response_model=AgreementResponse,
    summary="Get agreement detail (platform admin).",
)
async def admin_get_agreement(
    agreement_id: UUID,
    controller: AgreementsControllerDep,
    current_user: CurrentUserDep,
) -> AgreementResponse:
    return await controller.get(agreement_id, current_user)


@router.get(
    "/agreements/{agreement_id}/timeline",
    response_model=TimelineResponse,
    summary="Agreement timeline (platform admin).",
)
async def admin_agreement_timeline(
    agreement_id: UUID,
    controller: AgreementsControllerDep,
    current_user: CurrentUserDep,
) -> TimelineResponse:
    return await controller.timeline(agreement_id, current_user)


@router.get(
    "/agreements/{agreement_id}/progress",
    response_model=ProgressResponse,
    summary="Agreement progress (platform admin).",
)
async def admin_agreement_progress(
    agreement_id: UUID,
    controller: AgreementsControllerDep,
    current_user: CurrentUserDep,
) -> ProgressResponse:
    return await controller.progress(agreement_id, current_user)


@router.get(
    "/agreements/{agreement_id}/download/{artifact}",
    response_model=DownloadUrlResponse,
    summary="Download agreement artifact (platform admin).",
)
async def admin_download_agreement(
    agreement_id: UUID,
    artifact: str,
    controller: AgreementsControllerDep,
    current_user: CurrentUserDep,
    request: Request,
) -> DownloadUrlResponse:
    return await controller.download(agreement_id, artifact, current_user, request)


# ---------------------------------------------------------- notifications
def _build_notification_groups_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> AdminNotificationGroupsController:
    return build_admin_notification_groups_controller(db)


def _build_notification_campaigns_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> AdminNotificationCampaignsController:
    return build_admin_notification_campaigns_controller(db, redis_client)


NotificationGroupsControllerDep = Annotated[
    AdminNotificationGroupsController, Depends(_build_notification_groups_controller)
]
NotificationCampaignsControllerDep = Annotated[
    AdminNotificationCampaignsController,
    Depends(_build_notification_campaigns_controller),
]


async def _admin_user_id(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    current_user: CurrentUserDep,
) -> UUID:
    auth_repo = AuthRepository(db)
    user = await auth_repo.get_by_firebase_uid(current_user.uid)
    if user is None:
        from src.core.exceptions import NotFoundError

        raise NotFoundError("User not found.")
    return user.id


AdminUserIdDep = Annotated[UUID, Depends(_admin_user_id)]


@router.get(
    "/notification-groups",
    response_model=NotificationGroupListResponse,
    summary="List notification groups.",
)
async def list_notification_groups(
    controller: NotificationGroupsControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> NotificationGroupListResponse:
    return await controller.list(
        page=pagination.page, page_size=pagination.page_size
    )


@router.post(
    "/notification-groups",
    response_model=NotificationGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a notification group.",
)
async def create_notification_group(
    payload: NotificationGroupCreate,
    controller: NotificationGroupsControllerDep,
    admin_id: AdminUserIdDep,
) -> NotificationGroupResponse:
    return await controller.create(payload, created_by=admin_id)


@router.get(
    "/notification-groups/{group_id}",
    response_model=NotificationGroupResponse,
    summary="Get a notification group.",
)
async def get_notification_group(
    group_id: UUID,
    controller: NotificationGroupsControllerDep,
) -> NotificationGroupResponse:
    return await controller.get(group_id)


@router.patch(
    "/notification-groups/{group_id}",
    response_model=NotificationGroupResponse,
    summary="Update a notification group.",
)
async def update_notification_group(
    group_id: UUID,
    payload: NotificationGroupUpdate,
    controller: NotificationGroupsControllerDep,
) -> NotificationGroupResponse:
    return await controller.update(group_id, payload)


@router.delete(
    "/notification-groups/{group_id}",
    response_model=MessageResponse,
    summary="Delete a notification group.",
)
async def delete_notification_group(
    group_id: UUID,
    controller: NotificationGroupsControllerDep,
) -> MessageResponse:
    await controller.delete(group_id)
    return MessageResponse(message="Notification group deleted successfully.")


@router.get(
    "/notifications",
    response_model=NotificationCampaignListResponse,
    summary="List notification campaigns.",
)
async def list_notification_campaigns(
    controller: NotificationCampaignsControllerDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
) -> NotificationCampaignListResponse:
    return await controller.list(
        page=pagination.page, page_size=pagination.page_size
    )


@router.post(
    "/notifications",
    response_model=NotificationCampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and optionally send a notification campaign.",
)
async def create_notification_campaign(
    payload: NotificationCampaignCreate,
    controller: NotificationCampaignsControllerDep,
    current_user: CurrentUserDep,
) -> NotificationCampaignResponse:
    return await controller.create(payload, current_user)


@router.get(
    "/notifications/{campaign_id}",
    response_model=NotificationCampaignResponse,
    summary="Get a notification campaign.",
)
async def get_notification_campaign(
    campaign_id: UUID,
    controller: NotificationCampaignsControllerDep,
) -> NotificationCampaignResponse:
    return await controller.get(campaign_id)


@router.post(
    "/notifications/{campaign_id}/cancel",
    response_model=NotificationCampaignResponse,
    summary="Cancel a scheduled notification campaign.",
)
async def cancel_notification_campaign(
    campaign_id: UUID,
    controller: NotificationCampaignsControllerDep,
) -> NotificationCampaignResponse:
    return await controller.cancel(campaign_id)


@router.post(
    "/notifications/{campaign_id}/send-now",
    response_model=NotificationCampaignResponse,
    summary="Send a notification campaign immediately.",
)
async def send_notification_campaign_now(
    campaign_id: UUID,
    controller: NotificationCampaignsControllerDep,
) -> NotificationCampaignResponse:
    return await controller.send_now(campaign_id)


# ---------------------------------------------------------------------- blog
def _build_blog_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> AdminBlogController:
    return build_admin_blog_controller(db)


BlogControllerDep = Annotated[AdminBlogController, Depends(_build_blog_controller)]


@router.get(
    "/blog/posts",
    response_model=BlogPostListResponse,
    summary="List blog posts (admin).",
)
async def list_blog_posts(
    controller: BlogControllerDep,
    params: Annotated[BlogAdminListParams, Depends(BlogAdminListParams.as_query)],
) -> BlogPostListResponse:
    return await controller.list(params)


@router.post(
    "/blog/posts/images/upload",
    response_model=StorageUploadResponse,
    summary="Upload a blog cover image.",
)
async def upload_blog_cover(
    controller: BlogControllerDep,
    admin_id: AdminUserIdDep,
    file: UploadFile = File(...),
) -> StorageUploadResponse:
    return await controller.upload_cover(file, owner_id=admin_id)


@router.get(
    "/blog/posts/{post_id}",
    response_model=BlogPostResponse,
    summary="Get a blog post (admin).",
)
async def get_blog_post(
    post_id: UUID,
    controller: BlogControllerDep,
) -> BlogPostResponse:
    return await controller.get(post_id)


@router.post(
    "/blog/posts",
    response_model=BlogPostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a blog post.",
)
async def create_blog_post(
    payload: BlogPostCreate,
    controller: BlogControllerDep,
    admin_id: AdminUserIdDep,
) -> BlogPostResponse:
    return await controller.create(payload, created_by=admin_id)


@router.patch(
    "/blog/posts/{post_id}",
    response_model=BlogPostResponse,
    summary="Update a blog post.",
)
async def update_blog_post(
    post_id: UUID,
    payload: BlogPostUpdate,
    controller: BlogControllerDep,
) -> BlogPostResponse:
    return await controller.update(post_id, payload)


@router.delete(
    "/blog/posts/{post_id}",
    response_model=MessageResponse,
    summary="Delete a blog post.",
)
async def delete_blog_post(
    post_id: UUID,
    controller: BlogControllerDep,
) -> MessageResponse:
    return await controller.delete(post_id)


@router.post(
    "/blog/posts/{post_id}/publish",
    response_model=BlogPostResponse,
    summary="Publish a blog post immediately.",
)
async def publish_blog_post(
    post_id: UUID,
    controller: BlogControllerDep,
) -> BlogPostResponse:
    return await controller.publish(post_id)


@router.post(
    "/blog/posts/{post_id}/disable",
    response_model=BlogPostResponse,
    summary="Disable a blog post (410 on public slug).",
)
async def disable_blog_post(
    post_id: UUID,
    controller: BlogControllerDep,
) -> BlogPostResponse:
    return await controller.disable(post_id)


# ------------------------------------------------------------------ support
_SUPPORT_HEARTBEAT_SECONDS = 30


def _build_support_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> AdminSupportController:
    return build_admin_support_controller(db, redis_client)


SupportControllerDep = Annotated[
    AdminSupportController, Depends(_build_support_controller)
]


async def _support_ticket_event_stream(
    redis_client: Redis,
    ticket_id: UUID,
) -> AsyncIterator[str]:
    async for event in subscribe_support_ticket(redis_client, ticket_id):
        if event.get("type") == "ping":
            yield f"event: ping\ndata: {{}}\n\n"
            continue
        event_type = event.get("type", "message")
        yield f"event: {event_type}\ndata: {json.dumps(event.get('data', {}))}\n\n"


async def _support_admin_event_stream(
    redis_client: Redis,
    firebase_uid: str,
    auth_repo: AuthRepository,
    presence: PresenceService,
) -> AsyncIterator[str]:
    user = await auth_repo.get_by_firebase_uid(firebase_uid)
    if user is None:
        yield f"event: error\ndata: {json.dumps({'message': 'User not found'})}\n\n"
        return

    await presence.touch(user.id)
    async for event in subscribe_support_admin(redis_client):
        if event.get("type") == "ping":
            await presence.touch(user.id)
            yield f"event: ping\ndata: {{}}\n\n"
            continue
        event_type = event.get("type", "message")
        yield f"event: {event_type}\ndata: {json.dumps(event.get('data', {}))}\n\n"


@router.get(
    "/support/tickets",
    response_model=SupportTicketListResponse,
    summary="List all support tickets.",
)
async def list_support_tickets(
    controller: SupportControllerDep,
    params: Annotated[
        AdminSupportTicketListParams, Depends(AdminSupportTicketListParams.as_query)
    ],
) -> SupportTicketListResponse:
    return await controller.list_tickets(params)


@router.get(
    "/support/tickets/{ticket_id}",
    response_model=SupportTicketDetailResponse,
    summary="Get support ticket detail.",
)
async def get_support_ticket(
    ticket_id: UUID,
    controller: SupportControllerDep,
) -> SupportTicketDetailResponse:
    return await controller.get_ticket(ticket_id)


@router.get(
    "/support/tickets/{ticket_id}/messages",
    response_model=SupportMessageListResponse,
    summary="List all messages including internal notes.",
)
async def list_support_messages(
    ticket_id: UUID,
    controller: SupportControllerDep,
) -> SupportMessageListResponse:
    return await controller.list_messages(ticket_id)


@router.post(
    "/support/tickets/{ticket_id}/messages",
    response_model=SupportMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reply to the user.",
)
async def add_support_reply(
    ticket_id: UUID,
    payload: SupportMessageCreate,
    controller: SupportControllerDep,
    current_user: CurrentUserDep,
) -> SupportMessageResponse:
    return await controller.add_reply(ticket_id, payload, current_user)


@router.post(
    "/support/tickets/{ticket_id}/notes",
    response_model=SupportMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an internal note (admins only).",
)
async def add_support_note(
    ticket_id: UUID,
    payload: SupportInternalNoteCreate,
    controller: SupportControllerDep,
    current_user: CurrentUserDep,
) -> SupportMessageResponse:
    return await controller.add_note(ticket_id, payload, current_user)


@router.patch(
    "/support/tickets/{ticket_id}/assign",
    response_model=SupportTicketResponse,
    summary="Assign ticket to an admin.",
)
async def assign_support_ticket(
    ticket_id: UUID,
    payload: SupportTicketAssign,
    controller: SupportControllerDep,
    current_user: CurrentUserDep,
) -> SupportTicketResponse:
    return await controller.assign(ticket_id, payload, current_user)


@router.patch(
    "/support/tickets/{ticket_id}/close",
    response_model=SupportTicketResponse,
    summary="Close a support ticket.",
)
async def close_support_ticket(
    ticket_id: UUID,
    controller: SupportControllerDep,
    current_user: CurrentUserDep,
) -> SupportTicketResponse:
    return await controller.close(ticket_id, current_user)


@router.patch(
    "/support/tickets/{ticket_id}/reopen",
    response_model=SupportTicketResponse,
    summary="Reopen a closed support ticket.",
)
async def reopen_support_ticket(
    ticket_id: UUID,
    controller: SupportControllerDep,
    current_user: CurrentUserDep,
) -> SupportTicketResponse:
    return await controller.reopen(ticket_id, current_user)


@router.post(
    "/support/tickets/{ticket_id}/messages/read",
    response_model=SupportMessageListResponse,
    summary="Mark user messages as read by admin.",
)
async def mark_support_messages_read_admin(
    ticket_id: UUID,
    controller: SupportControllerDep,
) -> SupportMessageListResponse:
    return await controller.mark_messages_read(ticket_id)


@router.get(
    "/support/tickets/{ticket_id}/stream",
    summary="SSE stream of real-time events for a specific ticket.",
    status_code=status.HTTP_200_OK,
)
async def support_admin_ticket_stream(
    ticket_id: UUID,
    controller: SupportControllerDep,
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> StreamingResponse:
    await controller.get_ticket(ticket_id)

    async def _stream_with_heartbeat() -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _producer() -> None:
            try:
                async for chunk in _support_ticket_event_stream(redis_client, ticket_id):
                    await queue.put(chunk)
            except asyncio.CancelledError:
                await queue.put(None)
                raise
            except Exception:  # noqa: BLE001
                await queue.put(None)

        producer_task = asyncio.create_task(_producer())
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        queue.get(), timeout=_SUPPORT_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    yield f"event: ping\ndata: {{}}\n\n"
                    continue
                if chunk is None:
                    break
                yield chunk
        finally:
            producer_task.cancel()
            with suppress(asyncio.CancelledError):
                await producer_task

    return StreamingResponse(
        _stream_with_heartbeat(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/support/stream",
    summary="SSE stream of support events for admins.",
    status_code=status.HTTP_200_OK,
)
async def support_admin_stream(
    current_user: CurrentUserDep,
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> StreamingResponse:
    auth_repo = AuthRepository(db)
    support_service = build_support_service(db, redis_client)

    async def _stream_with_heartbeat() -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        await support_service.touch_presence(firebase_uid=current_user.uid)

        async def _producer() -> None:
            try:
                async for chunk in _support_admin_event_stream(
                    redis_client,
                    current_user.uid,
                    auth_repo,
                    PresenceService(redis_client),
                ):
                    await queue.put(chunk)
            except asyncio.CancelledError:
                await queue.put(None)
                raise
            except Exception:  # noqa: BLE001
                await queue.put(None)

        producer_task = asyncio.create_task(_producer())
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        queue.get(), timeout=_SUPPORT_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    await support_service.touch_presence(firebase_uid=current_user.uid)
                    yield f"event: ping\ndata: {{}}\n\n"
                    continue
                if chunk is None:
                    break
                yield chunk
        finally:
            producer_task.cancel()
            with suppress(asyncio.CancelledError):
                await producer_task

    return StreamingResponse(
        _stream_with_heartbeat(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
