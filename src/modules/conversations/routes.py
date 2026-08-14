"""User-facing opportunity conversation routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from src.infrastructure.realtime.conversation_pubsub import (
    subscribe_conversation_thread,
    subscribe_conversation_user,
)
from src.infrastructure.realtime.presence import PresenceService
from src.modules.auth.repository import AuthRepository
from src.modules.conversations.controller import UserConversationsController
from src.modules.conversations.deps import (
    build_conversations_service,
    build_user_conversations_controller,
)
from src.modules.conversations.schema import (
    ConversationCloseRequest,
    ConversationCreate,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationRequestNewContact,
    ConversationRequestReopen,
    ConversationRespondNewContact,
    ConversationRespondReopen,
    ConversationResponse,
    UserConversationListParams,
)
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/conversations", tags=["conversations"])

_HEARTBEAT_SECONDS = 30


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> UserConversationsController:
    return build_user_conversations_controller(db, redis_client)


ControllerDep = Annotated[UserConversationsController, Depends(_build_controller)]


async def _conversation_thread_event_stream(
    redis_client: Redis,
    conversation_id: UUID,
) -> AsyncIterator[str]:
    async for event in subscribe_conversation_thread(redis_client, conversation_id):
        if event.get("type") == "ping":
            yield "event: ping\ndata: {}\n\n"
            continue
        event_type = event.get("type", "message")
        yield f"event: {event_type}\ndata: {json.dumps(event.get('data', {}))}\n\n"


async def _conversation_user_event_stream(
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
    async for event in subscribe_conversation_user(redis_client, user.id):
        if event.get("type") == "ping":
            await presence.touch(user.id)
            yield "event: ping\ndata: {}\n\n"
            continue
        event_type = event.get("type", "message")
        yield f"event: {event_type}\ndata: {json.dumps(event.get('data', {}))}\n\n"


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Start or get a conversation on an opportunity.",
)
async def create_or_get_conversation(
    payload: ConversationCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.create_or_get(payload, current_user)


@router.get(
    "",
    response_model=ConversationListResponse,
    summary="List conversations for the current user.",
)
async def list_conversations(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    params: Annotated[
        UserConversationListParams, Depends(UserConversationListParams.as_query)
    ],
) -> ConversationListResponse:
    return await controller.list_conversations(params, current_user)


@router.get(
    "/stream",
    summary="SSE stream of conversation events for the current user.",
    status_code=status.HTTP_200_OK,
)
async def conversations_stream(
    current_user: CurrentUserDep,
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> StreamingResponse:
    auth_repo = AuthRepository(db)
    presence = PresenceService(redis_client)

    async def _stream_with_heartbeat() -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        user = await auth_repo.get_by_firebase_uid(current_user.uid)
        if user is not None:
            await presence.touch(user.id)

        async def _producer() -> None:
            try:
                async for chunk in _conversation_user_event_stream(
                    redis_client, current_user.uid, auth_repo, presence
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
                    if user is not None:
                        await presence.touch(user.id)
                    yield "event: ping\ndata: {}\n\n"
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
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get a conversation.",
)
async def get_conversation(
    conversation_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.get_conversation(conversation_id, current_user)


@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessageListResponse,
    summary="List messages visible to the participant.",
)
async def list_messages(
    conversation_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationMessageListResponse:
    return await controller.list_messages(conversation_id, current_user)


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message in a conversation.",
)
async def add_message(
    conversation_id: UUID,
    payload: ConversationMessageCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationMessageResponse:
    return await controller.add_message(conversation_id, payload, current_user)


@router.post(
    "/{conversation_id}/messages/read",
    response_model=ConversationMessageListResponse,
    summary="Mark counterpart messages as read.",
)
async def mark_messages_read(
    conversation_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationMessageListResponse:
    return await controller.mark_messages_read(conversation_id, current_user)


@router.post(
    "/{conversation_id}/close",
    response_model=ConversationResponse,
    summary="Close the contact between the parties.",
)
async def close_conversation(
    conversation_id: UUID,
    payload: ConversationCloseRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.close(conversation_id, payload, current_user)


@router.post(
    "/{conversation_id}/reopen",
    response_model=ConversationResponse,
    summary="Reopen a contact (only the user who closed it).",
)
async def reopen_conversation(
    conversation_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.reopen(conversation_id, current_user)


@router.post(
    "/{conversation_id}/request-reopen",
    response_model=ConversationResponse,
    summary="Request reopen of a closed contact.",
)
async def request_reopen(
    conversation_id: UUID,
    payload: ConversationRequestReopen,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.request_reopen(conversation_id, payload, current_user)


@router.post(
    "/{conversation_id}/respond-reopen",
    response_model=ConversationResponse,
    summary="Accept or reject a reopen request.",
)
async def respond_reopen(
    conversation_id: UUID,
    payload: ConversationRespondReopen,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.respond_reopen(conversation_id, payload, current_user)


@router.post(
    "/{conversation_id}/request-new-contact",
    response_model=ConversationResponse,
    summary="Request a new contact thread on the same opportunity.",
)
async def request_new_contact(
    conversation_id: UUID,
    payload: ConversationRequestNewContact,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.request_new_contact(
        conversation_id, payload, current_user
    )


@router.post(
    "/{conversation_id}/respond-new-contact",
    response_model=ConversationResponse,
    summary="Accept or reject a new-contact request.",
)
async def respond_new_contact(
    conversation_id: UUID,
    payload: ConversationRespondNewContact,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    return await controller.respond_new_contact(
        conversation_id, payload, current_user
    )


@router.get(
    "/{conversation_id}/stream",
    summary="SSE stream of real-time events for a specific conversation.",
    status_code=status.HTTP_200_OK,
)
async def conversation_thread_stream(
    conversation_id: UUID,
    current_user: CurrentUserDep,
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis_client: Annotated["Redis", Depends(get_redis)],
) -> StreamingResponse:
    service = build_conversations_service(db, redis_client)
    await service.get_user_conversation(conversation_id, firebase_uid=current_user.uid)

    async def _stream_with_heartbeat() -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _producer() -> None:
            try:
                async for chunk in _conversation_thread_event_stream(
                    redis_client, conversation_id
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
                    yield "event: ping\ndata: {}\n\n"
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
