"""AI provider contracts (embeddings, completions, OCR, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Embedding:
    vector: tuple[float, ...]
    model: str
    dimensions: int


@dataclass(slots=True, frozen=True)
class OCRResult:
    text: str
    pages: int
    confidence: float | None = None


class EmbeddingsProvider(ABC):
    """Provider for text embeddings (semantic search, RAG, clustering)."""

    @abstractmethod
    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[Embedding]:
        ...


class OCRProvider(ABC):
    """Provider for OCR / document text extraction."""

    @abstractmethod
    async def extract_text(self, data: bytes, *, mime_type: str) -> OCRResult:
        ...


class CompletionsProvider(ABC):
    """Provider for chat / completion calls used by AI agents."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        ...


__all__ = [
    "CompletionsProvider",
    "Embedding",
    "EmbeddingsProvider",
    "OCRProvider",
    "OCRResult",
]
