"""Per-request timeout middleware."""

from __future__ import annotations

import asyncio

from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import get_logger, request_id_ctx
from src.shared.schemas.responses import ErrorResponse

logger = get_logger(__name__)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Abort any request that exceeds ``timeout_seconds`` with a 504 response."""

    def __init__(self, app: object, *, timeout_seconds: float) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._timeout = timeout_seconds

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await asyncio.wait_for(call_next(request), timeout=self._timeout)
        except TimeoutError:
            logger.warning(
                "request_timeout",
                path=request.url.path,
                method=request.method,
                timeout_seconds=self._timeout,
            )
            payload = ErrorResponse(
                code="timeout",
                message="The request timed out.",
                request_id=request_id_ctx.get(),
            )
            return ORJSONResponse(status_code=504, content=payload.model_dump(mode="json"))


__all__ = ["TimeoutMiddleware"]
