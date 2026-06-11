"""HTTP controller for ``coming_soon``."""

from __future__ import annotations

from src.modules.coming_soon.schema import ComingSoonSubscribeRequest
from src.modules.coming_soon.service import ComingSoonService
from src.shared.schemas.responses import MessageResponse


class ComingSoonController:
    def __init__(self, service: ComingSoonService) -> None:
        self._service = service

    async def subscribe(self, payload: ComingSoonSubscribeRequest) -> MessageResponse:
        return await self._service.subscribe(payload)


__all__ = ["ComingSoonController"]
