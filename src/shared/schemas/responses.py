"""Common response envelopes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from src.shared.schemas.base import APIModel


class HealthResponse(APIModel):
    """Payload for ``GET /health`` and ``GET /health/ready``."""

    status: Literal["ok", "degraded", "down"] = "ok"
    checks: dict[str, str] | None = None


class ErrorResponse(APIModel):
    """Canonical error envelope returned by all global exception handlers."""

    code: str = Field(..., description="Stable, machine-readable error code.")
    message: str = Field(..., description="Human-readable description.")
    request_id: str | None = None
    details: dict[str, Any] | None = None


class MessageResponse(APIModel):
    """Generic success envelope for write endpoints that have no payload."""

    message: str
    data: dict[str, Any] | None = None


class StorageUploadResponse(APIModel):
    """Result of a server-side upload to Firebase Storage."""

    storage_key: str
    public_url: str


__all__ = ["ErrorResponse", "HealthResponse", "MessageResponse", "StorageUploadResponse"]
