"""Public routes for the ``blog`` module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends

from src.modules.blog.controller import PublicBlogController
from src.modules.blog.deps import build_public_blog_controller
from src.modules.blog.schema import (
    BlogPostExistsResponse,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPublicListParams,
)
from src.shared.dependencies.db import get_db

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/blog", tags=["blog"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> PublicBlogController:
    return build_public_blog_controller(db)


ControllerDep = Annotated[PublicBlogController, Depends(_build_controller)]


@router.get(
    "/posts/exists",
    response_model=BlogPostExistsResponse,
    summary="Check whether any published blog posts exist.",
)
async def posts_exist(controller: ControllerDep) -> BlogPostExistsResponse:
    return await controller.exists()


@router.get(
    "/posts",
    response_model=BlogPostListResponse,
    summary="List published blog posts.",
)
async def list_posts(
    controller: ControllerDep,
    params: Annotated[BlogPublicListParams, Depends(BlogPublicListParams.as_query)],
) -> BlogPostListResponse:
    return await controller.list(params)


@router.get(
    "/posts/{slug}",
    response_model=BlogPostResponse,
    summary="Get a published blog post by slug.",
)
async def get_post(slug: str, controller: ControllerDep) -> BlogPostResponse:
    return await controller.get_by_slug(slug)


__all__ = ["router"]
