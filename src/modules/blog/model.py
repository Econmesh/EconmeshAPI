"""Persistence models for blog posts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.schemas.base import DomainDocument


class BlogPostStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    DISABLED = "disabled"


class BlogPostSort(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"
    PUBLISH_AT_DESC = "publish_at_desc"
    PUBLISH_AT_ASC = "publish_at_asc"
    CREATED_AT_DESC = "created_at_desc"
    CREATED_AT_ASC = "created_at_asc"


class BlogCoverImage(BaseModel):
    storage_key: str
    public_url: str


class BlogPostDocument(DomainDocument):
    """A blog article managed by admins and published on the public site."""

    collection_name: ClassVar[str] = "blog_posts"

    title: str
    slug: str
    content: dict[str, Any] = Field(default_factory=dict)
    excerpt: str | None = None
    author: str | None = None
    cover_image: BlogCoverImage | None = None
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    status: BlogPostStatus = BlogPostStatus.DRAFT
    publish_at: datetime | None = None
    published_at: datetime | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    created_by: UUID | None = None


__all__ = [
    "BlogCoverImage",
    "BlogPostDocument",
    "BlogPostSort",
    "BlogPostStatus",
]
