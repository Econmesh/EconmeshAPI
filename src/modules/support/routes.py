"""User-facing support routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from src.infrastructure.realtime.presence import PresenceService
from src.infrastructure.realtime.support_pubsub import (
    subscribe_support_ticket,
    subscribe_support_user,
)
from src.modules.auth.repository import AuthRepository
from src.modules.support.controller import UserSupportController
from src.modules.support.deps import build_support_service, build_user_support_controller
from src.modules.support.schema import (
    SupportMessageCreate,
    SupportMessageListResponse,
    SupportMessageResponse,
    SupportTicketCreate,
    SupportTicketListResponse,
    SupportTicketResponse,
    UserSupportTicketListParams,
)
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis
from src.shared.schemas.responses import MessageResponse

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/support", tags=["support"])

_HEARTBEAT_SECONDS = 30


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> UserSupportController:
    return build_user_support_controller(db, redis_client)


ControllerDep = Annotated[UserSupportController, Depends(_build_controller)]


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


async def _support_user_event_stream(
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
    async for event in subscribe_support_user(redis_client, user.id):
        if event.get("type") == "ping":
            await presence.touch(user.id)
            yield f"event: ping\ndata: {{}}\n\n"
            continue
        event_type = event.get("type", "message")
        yield f"event: {event_type}\ndata: {json.dumps(event.get('data', {}))}\n\n"


@router.post(
    "/tickets",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a new support ticket.",
)
async def create_ticket(
    payload: SupportTicketCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> SupportTicketResponse:
    return await controller.create_ticket(payload, current_user)


@router.get(
    "/tickets",
    response_model=SupportTicketListResponse,
    summary="List support tickets for the current user.",
)
async def list_tickets(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    params: Annotated[UserSupportTicketListParams, Depends(UserSupportTicketListParams.as_query)],
) -> SupportTicketListResponse:
    return await controller.list_tickets(params, current_user)


@router.get(
    "/tickets/{ticket_id}",
    response_model=SupportTicketResponse,
    summary="Get a support ticket.",
)
async def get_ticket(
    ticket_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> SupportTicketResponse:
    return await controller.get_ticket(ticket_id, current_user)


@router.get(
    "/tickets/{ticket_id}/messages",
    response_model=SupportMessageListResponse,
    summary="List messages visible to the user.",
)
async def list_messages(
    ticket_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> SupportMessageListResponse:
    return await controller.list_messages(ticket_id, current_user)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=SupportMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message on a ticket.",
)
async def add_message(
    ticket_id: UUID,
    payload: SupportMessageCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> SupportMessageResponse:
    return await controller.add_message(ticket_id, payload, current_user)


@router.post(
    "/presence/heartbeat",
    response_model=MessageResponse,
    summary="Refresh online presence.",
)
async def presence_heartbeat(
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> MessageResponse:
    return await controller.heartbeat(current_user)


@router.post(
    "/presence/offline",
    response_model=MessageResponse,
    summary="Mark user as offline (e.g. on logout).",
)
async def presence_offline(
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> MessageResponse:
    return await controller.go_offline(current_user)


@router.post(
    "/tickets/{ticket_id}/messages/read",
    response_model=SupportMessageListResponse,
    summary="Mark admin replies as read by the user.",
)
async def mark_ticket_messages_read(
    ticket_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> SupportMessageListResponse:
    return await controller.mark_messages_read(ticket_id, current_user)


@router.get(
    "/stream",
    summary="SSE stream of support events for the current user.",
    status_code=status.HTTP_200_OK,
)
async def support_stream(
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
                async for chunk in _support_user_event_stream(
                    redis_client, current_user.uid, auth_repo, PresenceService(redis_client)
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


@router.get(
    "/tickets/{ticket_id}/stream",
    summary="SSE stream of real-time events for a specific ticket.",
    status_code=status.HTTP_200_OK,
)
async def support_ticket_stream(
    ticket_id: UUID,
    current_user: CurrentUserDep,
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> StreamingResponse:
    support_service = build_support_service(db, redis_client)
    await support_service.get_user_ticket(ticket_id, firebase_uid=current_user.uid)

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


__all__ = ["router"]
