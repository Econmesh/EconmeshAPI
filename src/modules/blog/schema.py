"""DTOs for the ``blog`` module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Query
from pydantic import Field, field_validator

from src.modules.blog.model import BlogPostSort, BlogPostStatus
from src.shared.schemas.base import APIModel


class BlogCoverImageInput(APIModel):
    storage_key: str = Field(..., min_length=1, max_length=500)
    public_url: str = Field(..., min_length=1, max_length=1000)


class BlogCoverImageResponse(APIModel):
    storage_key: str
    public_url: str


class BlogPostCreate(APIModel):
    title: str = Field(..., min_length=3, max_length=200)
    content: dict[str, Any] = Field(default_factory=dict)
    excerpt: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=120)
    cover_image: BlogCoverImageInput | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    category: str | None = Field(default=None, max_length=80)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    publish_at: datetime | None = None
    meta_title: str | None = Field(default=None, max_length=70)
    meta_description: str | None = Field(default=None, max_length=180)
    status: BlogPostStatus | None = None

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in value:
            t = tag.strip()
            if t and t not in cleaned:
                cleaned.append(t[:40])
        return cleaned


class BlogPostUpdate(APIModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    content: dict[str, Any] | None = None
    excerpt: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=120)
    cover_image: BlogCoverImageInput | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    category: str | None = Field(default=None, max_length=80)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    publish_at: datetime | None = None
    meta_title: str | None = Field(default=None, max_length=70)
    meta_description: str | None = Field(default=None, max_length=180)
    status: BlogPostStatus | None = None
    clear_cover_image: bool = False
    clear_publish_at: bool = False

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for tag in value:
            t = tag.strip()
            if t and t not in cleaned:
                cleaned.append(t[:40])
        return cleaned


class BlogPostResponse(APIModel):
    id: UUID
    title: str
    slug: str
    content: dict[str, Any]
    excerpt: str | None
    author: str | None
    cover_image: BlogCoverImageResponse | None
    tags: list[str]
    category: str | None
    status: BlogPostStatus
    publish_at: datetime | None
    published_at: datetime | None
    meta_title: str | None
    meta_description: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class BlogPostListItem(APIModel):
    id: UUID
    title: str
    slug: str
    excerpt: str | None
    author: str | None
    cover_image: BlogCoverImageResponse | None
    tags: list[str]
    category: str | None
    status: BlogPostStatus
    publish_at: datetime | None
    published_at: datetime | None
    meta_title: str | None
    meta_description: str | None
    created_at: datetime
    updated_at: datetime


class BlogPostListResponse(APIModel):
    items: list[BlogPostListItem]
    total: int
    page: int
    page_size: int
    has_more: bool = False


class BlogPostExistsResponse(APIModel):
    has_posts: bool


class BlogAdminListParams(APIModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    q: str | None = None
    status: BlogPostStatus | None = None
    sort: BlogPostSort = BlogPostSort.CREATED_AT_DESC

    @classmethod
    def as_query(
        cls,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        q: str | None = Query(None, max_length=200),
        status: BlogPostStatus | None = Query(None),
        sort: BlogPostSort = Query(BlogPostSort.CREATED_AT_DESC),
    ) -> BlogAdminListParams:
        return cls(page=page, page_size=page_size, q=q, status=status, sort=sort)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


class BlogPublicListParams(APIModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=50)
    q: str | None = None
    tag: str | None = None
    category: str | None = None
    sort: BlogPostSort = BlogPostSort.PUBLISH_AT_DESC

    @classmethod
    def as_query(
        cls,
        page: int = Query(1, ge=1),
        page_size: int = Query(12, ge=1, le=50),
        q: str | None = Query(None, max_length=200),
        tag: str | None = Query(None, max_length=40),
        category: str | None = Query(None, max_length=80),
        sort: BlogPostSort = Query(BlogPostSort.PUBLISH_AT_DESC),
    ) -> BlogPublicListParams:
        return cls(
            page=page,
            page_size=page_size,
            q=q,
            tag=tag,
            category=category,
            sort=sort,
        )

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


__all__ = [
    "BlogAdminListParams",
    "BlogCoverImageInput",
    "BlogCoverImageResponse",
    "BlogPostCreate",
    "BlogPostExistsResponse",
    "BlogPostListItem",
    "BlogPostListResponse",
    "BlogPostResponse",
    "BlogPostUpdate",
    "BlogPublicListParams",
]
