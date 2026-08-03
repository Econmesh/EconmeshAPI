"""Mongo repository for blog posts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.modules.blog.model import BlogPostDocument, BlogPostSort, BlogPostStatus
from src.modules.blog.schema import BlogAdminListParams, BlogPublicListParams
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from pymongo.asynchronous.collection import AsyncCollection


_SORT_MAP: dict[BlogPostSort, list[tuple[str, int]]] = {
    BlogPostSort.NEWEST: [("published_at", DESCENDING), ("created_at", DESCENDING)],
    BlogPostSort.OLDEST: [("published_at", ASCENDING), ("created_at", ASCENDING)],
    BlogPostSort.PUBLISH_AT_DESC: [
        ("published_at", DESCENDING),
        ("publish_at", DESCENDING),
        ("created_at", DESCENDING),
    ],
    BlogPostSort.PUBLISH_AT_ASC: [
        ("published_at", ASCENDING),
        ("publish_at", ASCENDING),
        ("created_at", ASCENDING),
    ],
    BlogPostSort.CREATED_AT_DESC: [("created_at", DESCENDING)],
    BlogPostSort.CREATED_AT_ASC: [("created_at", ASCENDING)],
}


class BlogPostsRepository:
    COLLECTION: str = BlogPostDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("slug", ASCENDING)],
            unique=True,
            name="ux_blog_posts_slug",
        )
        await self._collection.create_index(
            [("status", ASCENDING), ("publish_at", ASCENDING)],
            name="ix_blog_status_publish_at",
        )
        await self._collection.create_index(
            [("status", ASCENDING), ("published_at", DESCENDING)],
            name="ix_blog_status_published_at",
        )
        await self._collection.create_index(
            [("title", "text")],
            name="ix_blog_title_text",
        )
        await self._collection.create_index(
            [("created_at", DESCENDING)],
            name="ix_blog_created_at",
        )

    async def create(self, post: BlogPostDocument) -> BlogPostDocument:
        await self._collection.insert_one(post.to_mongo())
        return post

    async def get_by_id(self, post_id: UUID) -> BlogPostDocument | None:
        doc = await self._collection.find_one({"_id": post_id})
        return BlogPostDocument.model_validate(doc) if doc else None

    async def get_by_slug(self, slug: str) -> BlogPostDocument | None:
        doc = await self._collection.find_one({"slug": slug})
        return BlogPostDocument.model_validate(doc) if doc else None

    async def slug_exists(self, slug: str, *, exclude_id: UUID | None = None) -> bool:
        query: dict[str, Any] = {"slug": slug}
        if exclude_id is not None:
            query["_id"] = {"$ne": exclude_id}
        return await self._collection.find_one(query, projection={"_id": 1}) is not None

    async def update(
        self, post_id: UUID, patch: dict[str, Any]
    ) -> BlogPostDocument | None:
        patch = {**patch, "updated_at": utcnow()}
        doc = await self._collection.find_one_and_update(
            {"_id": post_id},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        return BlogPostDocument.model_validate(doc) if doc else None

    async def delete(self, post_id: UUID) -> bool:
        result = await self._collection.delete_one({"_id": post_id})
        return result.deleted_count > 0

    async def has_published(self) -> bool:
        doc = await self._collection.find_one(
            {"status": BlogPostStatus.PUBLISHED.value},
            projection={"_id": 1},
        )
        return doc is not None

    async def list_due_scheduled(
        self, *, now: datetime, limit: int = 50
    ) -> list[BlogPostDocument]:
        cursor = (
            self._collection.find(
                {
                    "status": BlogPostStatus.SCHEDULED.value,
                    "publish_at": {"$lte": now},
                }
            )
            .sort("publish_at", ASCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BlogPostDocument.model_validate(d) for d in docs]

    @staticmethod
    def _admin_filter(params: BlogAdminListParams) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if params.status is not None:
            query["status"] = params.status.value
        if params.q:
            escaped = re.escape(params.q.strip())
            query["title"] = {"$regex": escaped, "$options": "i"}
        return query

    @staticmethod
    def _public_filter(params: BlogPublicListParams) -> dict[str, Any]:
        query: dict[str, Any] = {"status": BlogPostStatus.PUBLISHED.value}
        if params.q:
            escaped = re.escape(params.q.strip())
            query["title"] = {"$regex": escaped, "$options": "i"}
        if params.tag:
            query["tags"] = params.tag.strip()
        if params.category:
            query["category"] = params.category.strip()
        return query

    async def list_admin(
        self, params: BlogAdminListParams
    ) -> list[BlogPostDocument]:
        query = self._admin_filter(params)
        sort = _SORT_MAP.get(params.sort, _SORT_MAP[BlogPostSort.CREATED_AT_DESC])
        cursor = (
            self._collection.find(query)
            .sort(sort)
            .skip(params.skip)
            .limit(params.page_size)
        )
        docs = await cursor.to_list(length=params.page_size)
        return [BlogPostDocument.model_validate(d) for d in docs]

    async def count_admin(self, params: BlogAdminListParams) -> int:
        return await self._collection.count_documents(self._admin_filter(params))

    async def list_public(
        self, params: BlogPublicListParams
    ) -> list[BlogPostDocument]:
        query = self._public_filter(params)
        sort = _SORT_MAP.get(params.sort, _SORT_MAP[BlogPostSort.PUBLISH_AT_DESC])
        cursor = (
            self._collection.find(query)
            .sort(sort)
            .skip(params.skip)
            .limit(params.page_size)
        )
        docs = await cursor.to_list(length=params.page_size)
        return [BlogPostDocument.model_validate(d) for d in docs]

    async def count_public(self, params: BlogPublicListParams) -> int:
        return await self._collection.count_documents(self._public_filter(params))

    async def list_all_published_for_sitemap(
        self, *, limit: int = 5_000
    ) -> list[BlogPostDocument]:
        cursor = (
            self._collection.find({"status": BlogPostStatus.PUBLISHED.value})
            .sort([("published_at", DESCENDING)])
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BlogPostDocument.model_validate(d) for d in docs]


__all__ = ["BlogPostsRepository"]
