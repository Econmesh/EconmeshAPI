"""Structured per-request access log."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import get_logger

logger = get_logger("access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit a single structured log line per request after the response is built."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1_000.0
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                query=request.url.query or None,
                status=status_code,
                duration_ms=round(duration_ms, 2),
                client=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )


__all__ = ["AccessLogMiddleware"]
