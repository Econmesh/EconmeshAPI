"""DTOs for the ``blockchain`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.blockchain.model import AnchorStatus
from src.shared.schemas.base import APIModel


class AnchorRequest(APIModel):
    network: str
    payload_hash: str = Field(..., min_length=64)
    subject_collection: str
    subject_id: UUID


class AnchorResponse(APIModel):
    id: UUID
    network: str
    payload_hash: str
    subject_collection: str
    subject_id: UUID
    tx_hash: str | None = None
    block_number: int | None = None
    status: AnchorStatus
    created_at: datetime
    updated_at: datetime


__all__ = ["AnchorRequest", "AnchorResponse"]
