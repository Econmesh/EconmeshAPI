"""User-facing notification routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from src.core.exceptions import NotFoundError
from src.infrastructure.realtime.redis_pubsub import subscribe_user_notifications
from src.modules.auth.repository import AuthRepository
from src.modules.notifications.controller import UserNotificationsController
from src.modules.notifications.repository import UserNotificationsRepository
from src.modules.notifications.schema import (
    UnreadCountResponse,
    UserNotificationListResponse,
    UserNotificationResponse,
)
from src.modules.notifications.service import UserNotificationsService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.pagination import PaginationParams
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/notifications", tags=["notifications"])

_HEARTBEAT_SECONDS = 30


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> UserNotificationsController:
    repo = UserNotificationsRepository(db)
    auth_repo = AuthRepository(db)
    service = UserNotificationsService(repo, auth_repo)
    return UserNotificationsController(service)


ControllerDep = Annotated[UserNotificationsController, Depends(_build_controller)]


async def _notification_event_stream(
    redis_client: Redis,
    firebase_uid: str,
    auth_repo: AuthRepository,
) -> AsyncIterator[str]:
    user = await auth_repo.get_by_firebase_uid(firebase_uid)
    if user is None:
        raise NotFoundError("User not found.")

    async for event in subscribe_user_notifications(redis_client, user.id):
        if event.get("type") == "ping":
            yield f"event: ping\ndata: {{}}\n\n"
            continue
        yield f"event: notification\ndata: {json.dumps(event.get('data', {}))}\n\n"


@router.get(
    "",
    response_model=UserNotificationListResponse,
    summary="List notifications for the current user.",
)
async def list_notifications(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    pagination: Annotated[PaginationParams, Depends(PaginationParams.as_query)],
    unread_only: bool = Query(default=False),
) -> UserNotificationListResponse:
    return await controller.list(
        current_user,
        page=pagination.page,
        page_size=pagination.page_size,
        unread_only=unread_only,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Unread notification count.",
)
async def unread_count(
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> UnreadCountResponse:
    return await controller.unread_count(current_user)


@router.patch(
    "/read-all",
    response_model=MessageResponse,
    summary="Mark all notifications as read.",
)
async def mark_all_read(
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> MessageResponse:
    count = await controller.mark_all_read(current_user)
    return MessageResponse(message=f"{count} notification(s) marked as read.")


@router.get(
    "/stream",
    summary="SSE stream of real-time notifications.",
    status_code=status.HTTP_200_OK,
)
async def notification_stream(
    current_user: CurrentUserDep,
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> StreamingResponse:
    auth_repo = AuthRepository(db)

    async def _stream_with_heartbeat() -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _producer() -> None:
            try:
                async for chunk in _notification_event_stream(
                    redis_client, current_user.uid, auth_repo
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
                        queue.get(), timeout=_HEARTBEAT_SECONDS
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


@router.patch(
    "/{notification_id}/read",
    response_model=UserNotificationResponse,
    summary="Mark a notification as read.",
)
async def mark_read(
    notification_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> UserNotificationResponse:
    return await controller.mark_read(notification_id, current_user)


__all__ = ["router"]
