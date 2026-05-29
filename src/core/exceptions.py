"""Domain-aware exception hierarchy and global FastAPI handlers.

All exceptions raised from services/repositories should subclass ``AppException``.
The HTTP layer never needs to know about ``HTTPException`` directly — the
registered handlers in ``register_exception_handlers`` translate everything into
the canonical ``ErrorResponse`` shape with a stable ``code`` and the current
``request_id``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.logging import get_logger, request_id_ctx
from src.shared.schemas.responses import ErrorResponse

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------
class AppException(Exception):
    """Base for all domain exceptions raised inside the application."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)


class AuthError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "Authentication required or token is invalid."


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to access this resource."


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class ValidationAppError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"
    message = "The request payload is invalid."


class RateLimitError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Slow down."


class ExternalServiceError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "external_service_error"
    message = "An upstream service failed to respond correctly."


class TimeoutAppError(AppException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "timeout"
    message = "The operation timed out."


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def _build_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ORJSONResponse:
    payload = ErrorResponse(
        code=code,
        message=message,
        request_id=request_id_ctx.get(),
        details=details,
    )
    return ORJSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


async def _app_exception_handler(_request: Request, exc: AppException) -> ORJSONResponse:
    logger.warning(
        "app_exception",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )
    return _build_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details or None,
    )


async def _validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> ORJSONResponse:
    logger.info("validation_error", errors=exc.errors())
    return _build_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Request validation failed.",
        details={"errors": exc.errors()},
    )


async def _http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> ORJSONResponse:
    return _build_response(
        status_code=exc.status_code,
        code="http_error",
        message=str(exc.detail),
    )


async def _unhandled_exception_handler(
    _request: Request, exc: Exception
) -> ORJSONResponse:
    logger.exception("unhandled_exception", exc_type=type(exc).__name__)
    return _build_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred. Please contact support.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire global handlers onto the FastAPI app."""
    app.add_exception_handler(AppException, _app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)


__all__ = [
    "AppException",
    "AuthError",
    "ConflictError",
    "ExternalServiceError",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitError",
    "TimeoutAppError",
    "ValidationAppError",
    "register_exception_handlers",
]
