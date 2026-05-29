"""Pagination helpers."""

from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Common ``skip``/``limit`` pagination input.

    Usage in a FastAPI route::

        @router.get(...)
        async def list_items(pagination: PaginationParams = Depends()): ...
    """

    page: int = Field(default=1, ge=1, description="1-based page index.")
    page_size: int = Field(default=20, ge=1, le=200, description="Items per page.")

    @classmethod
    def as_query(
        cls,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
    ) -> "PaginationParams":
        return cls(page=page, page_size=page_size)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class Page(BaseModel, Generic[T]):
    """Generic page envelope returned by list endpoints."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)

    @property
    def pages(self) -> int:
        if self.page_size == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


__all__ = ["Page", "PaginationParams"]
