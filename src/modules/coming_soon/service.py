"""Business rules for coming-soon email signups."""

from __future__ import annotations

from src.core.logging import get_logger
from src.modules.coming_soon.model import ComingSoonSubscriberDocument
from src.modules.coming_soon.repository import ComingSoonRepository
from src.modules.coming_soon.schema import ComingSoonSubscribeRequest
from src.shared.schemas.responses import MessageResponse

logger = get_logger(__name__)

_SUCCESS_MESSAGE = "Thanks! We'll notify you when we launch."


class ComingSoonService:
    def __init__(self, repository: ComingSoonRepository) -> None:
        self._repo = repository

    async def subscribe(self, payload: ComingSoonSubscribeRequest) -> MessageResponse:
        email = str(payload.email).lower()
        existing = await self._repo.get_by_email(email)
        if existing is not None:
            return MessageResponse(message=_SUCCESS_MESSAGE)

        subscriber = ComingSoonSubscriberDocument(email=email)
        await self._repo.create(subscriber)
        logger.info("coming_soon_subscribed", subscriber_id=str(subscriber.id))
        return MessageResponse(message=_SUCCESS_MESSAGE)


__all__ = ["ComingSoonService"]
