"""HTTP controllers for blog posts."""

from __future__ import annotations

from uuid import UUID

from fastapi import UploadFile

from src.modules.blog.schema import (
    BlogAdminListParams,
    BlogPostCreate,
    BlogPostExistsResponse,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPostUpdate,
    BlogPublicListParams,
)
from src.modules.blog.service import BlogService
from src.shared.schemas.responses import MessageResponse, StorageUploadResponse


class PublicBlogController:
    def __init__(self, service: BlogService) -> None:
        self._service = service

    async def list(
        self, params: BlogPublicListParams
    ) -> BlogPostListResponse:
        return await self._service.list_public(params)

    async def get_by_slug(self, slug: str) -> BlogPostResponse:
        return await self._service.get_public_by_slug(slug)

    async def exists(self) -> BlogPostExistsResponse:
        return await self._service.exists_published()


class AdminBlogController:
    def __init__(self, service: BlogService) -> None:
        self._service = service

    async def list(self, params: BlogAdminListParams) -> BlogPostListResponse:
        return await self._service.list_admin(params)

    async def get(self, post_id: UUID) -> BlogPostResponse:
        return await self._service.get_admin(post_id)

    async def create(
        self, payload: BlogPostCreate, *, created_by: UUID
    ) -> BlogPostResponse:
        return await self._service.create(payload, created_by=created_by)

    async def update(
        self, post_id: UUID, payload: BlogPostUpdate
    ) -> BlogPostResponse:
        return await self._service.update(post_id, payload)

    async def delete(self, post_id: UUID) -> MessageResponse:
        return await self._service.delete(post_id)

    async def publish(self, post_id: UUID) -> BlogPostResponse:
        return await self._service.publish(post_id)

    async def disable(self, post_id: UUID) -> BlogPostResponse:
        return await self._service.disable(post_id)

    async def upload_cover(
        self, file: UploadFile, *, owner_id: UUID
    ) -> StorageUploadResponse:
        return await self._service.upload_cover(file, owner_id=owner_id)


__all__ = ["AdminBlogController", "PublicBlogController"]
