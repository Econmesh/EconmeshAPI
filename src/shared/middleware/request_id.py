"""Inject and propagate a unique request ID for every HTTP request."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import request_id_ctx, trace_id_ctx
from src.shared.constants.http import REQUEST_ID_HEADER, TRACE_ID_HEADER


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Read or generate ``X-Request-ID``; expose it via contextvars + response header.

    A ``X-Trace-ID`` header is also honoured to integrate with an upstream tracer.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        trace_id = request.headers.get(TRACE_ID_HEADER) or request_id

        rid_token = request_id_ctx.set(request_id)
        tid_token = trace_id_ctx.set(trace_id)

        request.state.request_id = request_id
        request.state.trace_id = trace_id

        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(rid_token)
            trace_id_ctx.reset(tid_token)

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[TRACE_ID_HEADER] = trace_id
        return response


__all__ = ["RequestIDMiddleware"]
