"""Persistence model for blockchain anchors."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import Field

from src.shared.schemas.base import DomainDocument


class AnchorStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class BlockchainAnchorDocument(DomainDocument):
    """A record of a payload anchored on a blockchain network."""

    collection_name: ClassVar[str] = "blockchain_anchors"

    network: str = Field(..., description="e.g. polygon, ethereum, hyperledger-fabric")
    payload_hash: str = Field(..., min_length=64, description="Hex-encoded SHA-256.")
    subject_collection: str
    subject_id: UUID
    tx_hash: str | None = None
    block_number: int | None = None
    status: AnchorStatus = AnchorStatus.PENDING
    raw_receipt: dict[str, Any] | None = None


__all__ = ["AnchorStatus", "BlockchainAnchorDocument"]
