"""Persistence models for visual signatures and rubrics."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument

GENERATION_VERSION = "v1"


class VisualSignatureKind(StrEnum):
    SIGNATURE = "signature"
    INITIALS = "initials"


class VisualSignatureSource(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class VisualSignatureEventType(StrEnum):
    CREATED = "created"
    USED_IN_AGREEMENT = "used_in_agreement"
    INTEGRITY_FAILED = "integrity_failed"


class VisualSignatureDocument(DomainDocument):
    """Immutable visual signature or rubric bound to a user."""

    collection_name: ClassVar[str] = "user_visual_signatures"

    user_id: UUID
    kind: VisualSignatureKind
    source: VisualSignatureSource
    font_id: str | None = None
    source_text_enc: str
    uniqueness_hmac: str | None = None
    storage_key: str
    sha256: str
    content_type: str = "image/png"
    width: int
    height: int
    generation_version: str = GENERATION_VERSION
    ip: str | None = None
    user_agent: str | None = None


class VisualSignatureEventDocument(DomainDocument):
    """Append-only audit trail for visual signature operations."""

    collection_name: ClassVar[str] = "visual_signature_events"

    signature_id: UUID
    user_id: UUID
    event_type: VisualSignatureEventType
    ip: str | None = None
    user_agent: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "GENERATION_VERSION",
    "VisualSignatureDocument",
    "VisualSignatureEventDocument",
    "VisualSignatureEventType",
    "VisualSignatureKind",
    "VisualSignatureSource",
]
