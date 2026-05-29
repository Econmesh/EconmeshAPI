"""Blockchain provider contracts (on-chain registry / proof anchoring)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class OnChainReceipt:
    tx_hash: str
    block_number: int | None
    network: str
    timestamp_unix: int
    raw: dict[str, Any]


class BlockchainProvider(ABC):
    """Async contract for anchoring data hashes / events on-chain.

    Concrete impls might wrap web3.py + an EVM RPC, a Hyperledger Fabric SDK,
    a managed service like Polygon ID, etc.
    """

    @abstractmethod
    async def anchor_hash(self, payload_hash: str, *, metadata: dict[str, Any] | None = None) -> OnChainReceipt:
        """Anchor a hex-encoded hash on-chain and return the transaction receipt."""

    @abstractmethod
    async def verify_anchor(self, tx_hash: str) -> OnChainReceipt | None:
        """Look up a previously-anchored transaction (returns ``None`` if absent)."""


__all__ = ["BlockchainProvider", "OnChainReceipt"]
