"""Dependency wiring for blog services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.blog.controller import AdminBlogController, PublicBlogController
from src.modules.blog.repository import BlogPostsRepository
from src.modules.blog.service import BlogService

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


def build_blog_service(db: AsyncDatabase) -> BlogService:
    return BlogService(BlogPostsRepository(db))


def build_public_blog_controller(db: AsyncDatabase) -> PublicBlogController:
    return PublicBlogController(build_blog_service(db))


def build_admin_blog_controller(db: AsyncDatabase) -> AdminBlogController:
    return AdminBlogController(build_blog_service(db))


__all__ = [
    "build_admin_blog_controller",
    "build_blog_service",
    "build_public_blog_controller",
]
