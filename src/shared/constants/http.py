"""HTTP-related constants used across the API."""

from __future__ import annotations

REQUEST_ID_HEADER: str = "X-Request-ID"
TRACE_ID_HEADER: str = "X-Trace-ID"
RATE_LIMIT_HEADER: str = "X-RateLimit-Limit"

# Standardised messages used by the error layer.
MSG_INVALID_TOKEN: str = "The provided authentication token is invalid or expired."
MSG_MISSING_TOKEN: str = "Authentication token is missing."
MSG_FORBIDDEN: str = "You do not have permission to access this resource."


__all__ = [
    "MSG_FORBIDDEN",
    "MSG_INVALID_TOKEN",
    "MSG_MISSING_TOKEN",
    "RATE_LIMIT_HEADER",
    "REQUEST_ID_HEADER",
    "TRACE_ID_HEADER",
]
