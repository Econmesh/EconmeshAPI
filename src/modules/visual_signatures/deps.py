"""Dependency wiring for visual signatures."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.auth.repository import AuthRepository
from src.modules.visual_signatures.repository import (
    VisualSignatureEventsRepository,
    VisualSignaturesRepository,
)
from src.modules.visual_signatures.service import VisualSignaturesService

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


def build_visual_signatures_service(db: AsyncDatabase) -> VisualSignaturesService:
    return VisualSignaturesService(
        VisualSignaturesRepository(db),
        VisualSignatureEventsRepository(db),
        AuthRepository(db),
    )


__all__ = ["build_visual_signatures_service"]
