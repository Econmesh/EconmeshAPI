"""DTOs for visual signatures and rubrics."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.visual_signatures.model import (
    VisualSignatureKind,
    VisualSignatureSource,
)
from src.shared.schemas.base import APIModel


class FontOptionResponse(APIModel):
    id: str
    name: str


class InitialsOptionResponse(APIModel):
    id: str
    label: str
    text: str


class VisualSignaturePreviewRequest(APIModel):
    kind: VisualSignatureKind
    font_id: str = Field(..., min_length=1, max_length=64)
    text_variant: str | None = Field(default=None, max_length=64)


class VisualSignaturePreviewResponse(APIModel):
    unique: bool
    kind: VisualSignatureKind
    font_id: str
    source_text: str
    image_base64: str
    content_type: str = "image/png"
    width: int
    height: int


class VisualSignatureConfirmRequest(APIModel):
    kind: VisualSignatureKind
    font_id: str = Field(..., min_length=1, max_length=64)
    text_variant: str | None = Field(default=None, max_length=64)


class VisualSignatureResponse(APIModel):
    id: UUID
    kind: VisualSignatureKind
    source: VisualSignatureSource
    font_id: str | None = None
    source_text: str
    sha256: str
    width: int
    height: int
    generation_version: str
    created_at: datetime


class VisualSignaturesBundleResponse(APIModel):
    signature: VisualSignatureResponse | None = None
    initials: VisualSignatureResponse | None = None


__all__ = [
    "FontOptionResponse",
    "InitialsOptionResponse",
    "VisualSignatureConfirmRequest",
    "VisualSignaturePreviewRequest",
    "VisualSignaturePreviewResponse",
    "VisualSignatureResponse",
    "VisualSignaturesBundleResponse",
]
