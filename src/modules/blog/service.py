"""Business logic for blog posts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import UploadFile

from src.core.exceptions import ConflictError, GoneError, NotFoundError, ValidationAppError
from src.modules.blog.model import (
    BlogCoverImage,
    BlogPostDocument,
    BlogPostStatus,
)
from src.modules.blog.repository import BlogPostsRepository
from src.modules.blog.schema import (
    BlogAdminListParams,
    BlogCoverImageResponse,
    BlogPostCreate,
    BlogPostExistsResponse,
    BlogPostListItem,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPostUpdate,
    BlogPublicListParams,
)
from src.shared.schemas.responses import MessageResponse, StorageUploadResponse
from src.shared.utils.image_upload import extension_from_filename, upload_image_file
from src.shared.utils.slugify import slugify
from src.shared.utils.storage_keys import build_storage_key
from src.shared.utils.time import utcnow

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

_ALLOWED_NODES = frozenset(
    {
        "doc",
        "paragraph",
        "text",
        "heading",
        "bulletList",
        "orderedList",
        "listItem",
        "blockquote",
        "codeBlock",
        "hardBreak",
        "horizontalRule",
        "image",
        "table",
        "tableRow",
        "tableCell",
        "tableHeader",
    }
)
_ALLOWED_MARKS = frozenset({"bold", "italic", "underline", "strike", "code", "link"})
_ALLOWED_MARK_ATTRS = {
    "link": frozenset({"href", "target", "rel", "class"}),
}
_ALLOWED_NODE_ATTRS = {
    "heading": frozenset({"level"}),
    "image": frozenset({"src", "alt", "title"}),
    "codeBlock": frozenset({"language"}),
}


def sanitize_tiptap_json(content: dict[str, Any] | None) -> dict[str, Any]:
    """Whitelist TipTap nodes/marks to reduce XSS risk before persistence."""
    if not content or not isinstance(content, dict):
        return {"type": "doc", "content": []}

    def _clean_marks(marks: list[Any] | None) -> list[dict[str, Any]] | None:
        if not marks:
            return None
        cleaned: list[dict[str, Any]] = []
        for mark in marks:
            if not isinstance(mark, dict):
                continue
            mark_type = mark.get("type")
            if mark_type not in _ALLOWED_MARKS:
                continue
            attrs = mark.get("attrs")
            allowed = _ALLOWED_MARK_ATTRS.get(str(mark_type))
            if isinstance(attrs, dict) and allowed is not None:
                attrs = {k: v for k, v in attrs.items() if k in allowed}
                if mark_type == "link":
                    href = attrs.get("href")
                    if not isinstance(href, str) or not (
                        href.startswith("http://")
                        or href.startswith("https://")
                        or href.startswith("mailto:")
                        or href.startswith("/")
                    ):
                        continue
                    attrs.setdefault("rel", "noopener noreferrer")
            entry: dict[str, Any] = {"type": mark_type}
            if attrs:
                entry["attrs"] = attrs
            cleaned.append(entry)
        return cleaned or None

    def _clean_node(node: Any) -> dict[str, Any] | None:
        if not isinstance(node, dict):
            return None
        node_type = node.get("type")
        if node_type not in _ALLOWED_NODES:
            return None
        result: dict[str, Any] = {"type": node_type}
        if "text" in node and isinstance(node["text"], str):
            result["text"] = node["text"]
        attrs = node.get("attrs")
        allowed_attrs = _ALLOWED_NODE_ATTRS.get(str(node_type))
        if isinstance(attrs, dict) and allowed_attrs is not None:
            filtered = {k: v for k, v in attrs.items() if k in allowed_attrs}
            if node_type == "image":
                src = filtered.get("src")
                if not isinstance(src, str) or not (
                    src.startswith("http://")
                    or src.startswith("https://")
                    or src.startswith("/")
                ):
                    return None
            if filtered:
                result["attrs"] = filtered
        marks = _clean_marks(node.get("marks"))
        if marks:
            result["marks"] = marks
        children = node.get("content")
        if isinstance(children, list):
            cleaned_children = [
                c for c in (_clean_node(child) for child in children) if c is not None
            ]
            if cleaned_children:
                result["content"] = cleaned_children
        return result

    root = _clean_node(content)
    if root is None or root.get("type") != "doc":
        return {"type": "doc", "content": []}
    return root


def _cover_to_response(
    cover: BlogCoverImage | None,
) -> BlogCoverImageResponse | None:
    if cover is None:
        return None
    return BlogCoverImageResponse(
        storage_key=cover.storage_key,
        public_url=cover.public_url,
    )


def _to_response(doc: BlogPostDocument) -> BlogPostResponse:
    return BlogPostResponse(
        id=doc.id,
        title=doc.title,
        slug=doc.slug,
        content=doc.content,
        excerpt=doc.excerpt,
        author=doc.author,
        cover_image=_cover_to_response(doc.cover_image),
        tags=list(doc.tags),
        category=doc.category,
        status=doc.status,
        publish_at=doc.publish_at,
        published_at=doc.published_at,
        meta_title=doc.meta_title,
        meta_description=doc.meta_description,
        created_by=doc.created_by,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _to_list_item(doc: BlogPostDocument) -> BlogPostListItem:
    return BlogPostListItem(
        id=doc.id,
        title=doc.title,
        slug=doc.slug,
        excerpt=doc.excerpt,
        author=doc.author,
        cover_image=_cover_to_response(doc.cover_image),
        tags=list(doc.tags),
        category=doc.category,
        status=doc.status,
        publish_at=doc.publish_at,
        published_at=doc.published_at,
        meta_title=doc.meta_title,
        meta_description=doc.meta_description,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class BlogService:
    def __init__(self, repository: BlogPostsRepository) -> None:
        self._repo = repository

    async def _unique_slug(
        self, base: str, *, exclude_id: UUID | None = None
    ) -> str:
        candidate = slugify(base)
        if not await self._repo.slug_exists(candidate, exclude_id=exclude_id):
            return candidate
        for i in range(2, 200):
            numbered = f"{candidate}-{i}"
            if not await self._repo.slug_exists(numbered, exclude_id=exclude_id):
                return numbered
        raise ConflictError("Unable to allocate a unique slug.")

    def _resolve_create_status(
        self,
        *,
        requested: BlogPostStatus | None,
        publish_at,
    ) -> tuple[BlogPostStatus, Any, Any]:
        now = utcnow()
        published_at = None
        status = requested or BlogPostStatus.DRAFT

        if status is BlogPostStatus.DISABLED:
            return status, publish_at, None

        if status is BlogPostStatus.PUBLISHED:
            return BlogPostStatus.PUBLISHED, publish_at or now, now

        if publish_at is not None and publish_at > now:
            return BlogPostStatus.SCHEDULED, publish_at, None

        if status is BlogPostStatus.SCHEDULED:
            if publish_at is None:
                raise ValidationAppError(
                    "publish_at is required when status is scheduled."
                )
            if publish_at <= now:
                return BlogPostStatus.PUBLISHED, publish_at, now
            return BlogPostStatus.SCHEDULED, publish_at, None

        return BlogPostStatus.DRAFT, publish_at, published_at

    async def create(
        self, payload: BlogPostCreate, *, created_by: UUID
    ) -> BlogPostResponse:
        status, publish_at, published_at = self._resolve_create_status(
            requested=payload.status,
            publish_at=payload.publish_at,
        )
        base_slug = payload.slug or payload.title
        slug = await self._unique_slug(base_slug)
        cover = None
        if payload.cover_image is not None:
            cover = BlogCoverImage(
                storage_key=payload.cover_image.storage_key,
                public_url=payload.cover_image.public_url,
            )
        doc = BlogPostDocument(
            title=payload.title.strip(),
            slug=slug,
            content=sanitize_tiptap_json(payload.content),
            excerpt=payload.excerpt,
            author=payload.author,
            cover_image=cover,
            tags=list(payload.tags),
            category=payload.category,
            status=status,
            publish_at=publish_at,
            published_at=published_at,
            meta_title=payload.meta_title,
            meta_description=payload.meta_description,
            created_by=created_by,
        )
        created = await self._repo.create(doc)
        return _to_response(created)

    async def update(self, post_id: UUID, payload: BlogPostUpdate) -> BlogPostResponse:
        existing = await self._repo.get_by_id(post_id)
        if existing is None:
            raise NotFoundError("Blog post not found.")

        patch: dict[str, Any] = {}
        data = payload.model_dump(exclude_unset=True)

        if "title" in data and data["title"] is not None:
            patch["title"] = data["title"].strip()
        if "content" in data and data["content"] is not None:
            patch["content"] = sanitize_tiptap_json(data["content"])
        for field in (
            "excerpt",
            "author",
            "category",
            "meta_title",
            "meta_description",
            "tags",
        ):
            if field in data:
                patch[field] = data[field]

        if payload.clear_cover_image:
            patch["cover_image"] = None
        elif "cover_image" in data and data["cover_image"] is not None:
            patch["cover_image"] = BlogCoverImage(
                storage_key=data["cover_image"]["storage_key"],
                public_url=data["cover_image"]["public_url"],
            ).model_dump()

        if payload.clear_publish_at:
            patch["publish_at"] = None
        elif "publish_at" in data:
            patch["publish_at"] = data["publish_at"]

        if "slug" in data and data["slug"]:
            patch["slug"] = await self._unique_slug(
                data["slug"], exclude_id=post_id
            )

        next_status = data.get("status", existing.status)
        if isinstance(next_status, str):
            next_status = BlogPostStatus(next_status)
        publish_at = patch.get("publish_at", existing.publish_at)
        if payload.clear_publish_at:
            publish_at = None

        now = utcnow()
        if next_status is BlogPostStatus.PUBLISHED:
            patch["status"] = BlogPostStatus.PUBLISHED.value
            patch["published_at"] = existing.published_at or now
            if publish_at is None:
                patch["publish_at"] = now
        elif next_status is BlogPostStatus.SCHEDULED:
            if publish_at is None:
                raise ValidationAppError(
                    "publish_at is required when status is scheduled."
                )
            if publish_at <= now:
                patch["status"] = BlogPostStatus.PUBLISHED.value
                patch["published_at"] = existing.published_at or now
            else:
                patch["status"] = BlogPostStatus.SCHEDULED.value
                patch["published_at"] = None
        elif next_status is BlogPostStatus.DISABLED:
            patch["status"] = BlogPostStatus.DISABLED.value
        elif next_status is BlogPostStatus.DRAFT:
            patch["status"] = BlogPostStatus.DRAFT.value
            patch["published_at"] = None
        elif "status" in data:
            patch["status"] = next_status.value

        # Auto-schedule when draft gains a future publish_at without explicit status.
        if (
            "status" not in data
            and publish_at is not None
            and publish_at > now
            and existing.status
            in {BlogPostStatus.DRAFT, BlogPostStatus.SCHEDULED}
        ):
            patch["status"] = BlogPostStatus.SCHEDULED.value
            patch["published_at"] = None

        updated = await self._repo.update(post_id, patch)
        if updated is None:
            raise NotFoundError("Blog post not found.")
        return _to_response(updated)

    async def get_admin(self, post_id: UUID) -> BlogPostResponse:
        doc = await self._repo.get_by_id(post_id)
        if doc is None:
            raise NotFoundError("Blog post not found.")
        return _to_response(doc)

    async def delete(self, post_id: UUID) -> MessageResponse:
        deleted = await self._repo.delete(post_id)
        if not deleted:
            raise NotFoundError("Blog post not found.")
        return MessageResponse(message="Blog post deleted successfully.")

    async def publish(self, post_id: UUID) -> BlogPostResponse:
        existing = await self._repo.get_by_id(post_id)
        if existing is None:
            raise NotFoundError("Blog post not found.")
        now = utcnow()
        updated = await self._repo.update(
            post_id,
            {
                "status": BlogPostStatus.PUBLISHED.value,
                "published_at": existing.published_at or now,
                "publish_at": existing.publish_at or now,
            },
        )
        if updated is None:
            raise NotFoundError("Blog post not found.")
        return _to_response(updated)

    async def disable(self, post_id: UUID) -> BlogPostResponse:
        existing = await self._repo.get_by_id(post_id)
        if existing is None:
            raise NotFoundError("Blog post not found.")
        updated = await self._repo.update(
            post_id, {"status": BlogPostStatus.DISABLED.value}
        )
        if updated is None:
            raise NotFoundError("Blog post not found.")
        return _to_response(updated)

    async def list_admin(
        self, params: BlogAdminListParams
    ) -> BlogPostListResponse:
        items = await self._repo.list_admin(params)
        total = await self._repo.count_admin(params)
        return BlogPostListResponse(
            items=[_to_list_item(d) for d in items],
            total=total,
            page=params.page,
            page_size=params.page_size,
            has_more=(params.page * params.page_size) < total,
        )

    async def list_public(
        self, params: BlogPublicListParams
    ) -> BlogPostListResponse:
        items = await self._repo.list_public(params)
        total = await self._repo.count_public(params)
        return BlogPostListResponse(
            items=[_to_list_item(d) for d in items],
            total=total,
            page=params.page,
            page_size=params.page_size,
            has_more=(params.page * params.page_size) < total,
        )

    async def get_public_by_slug(self, slug: str) -> BlogPostResponse:
        doc = await self._repo.get_by_slug(slug)
        if doc is None:
            raise NotFoundError("Blog post not found.")
        if doc.status is BlogPostStatus.DISABLED:
            raise GoneError("This blog post has been removed.")
        if doc.status is not BlogPostStatus.PUBLISHED:
            raise NotFoundError("Blog post not found.")
        return _to_response(doc)

    async def exists_published(self) -> BlogPostExistsResponse:
        return BlogPostExistsResponse(has_posts=await self._repo.has_published())

    async def publish_due_scheduled(self) -> int:
        """Flip due scheduled posts to published. Returns count processed."""
        now = utcnow()
        due = await self._repo.list_due_scheduled(now=now)
        count = 0
        for post in due:
            await self._repo.update(
                post.id,
                {
                    "status": BlogPostStatus.PUBLISHED.value,
                    "published_at": now,
                },
            )
            count += 1
        return count

    async def upload_cover(
        self, file: UploadFile, *, owner_id: UUID
    ) -> StorageUploadResponse:
        extension = extension_from_filename(file.filename or "image.bin")
        storage_key = build_storage_key("blog", owner_id, extension)
        public_url = await upload_image_file(
            file,
            allowed_types=_ALLOWED_IMAGE_TYPES,
            storage_key=storage_key,
        )
        return StorageUploadResponse(storage_key=storage_key, public_url=public_url)


__all__ = ["BlogService", "sanitize_tiptap_json"]
