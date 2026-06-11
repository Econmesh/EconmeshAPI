"""Persistence model for the ``coming_soon_subscribers`` collection."""

from __future__ import annotations

from typing import ClassVar

from pydantic import EmailStr, Field

from src.shared.schemas.base import DomainDocument


class ComingSoonSubscriberDocument(DomainDocument):
    """An email address registered for coming-soon launch notifications."""

    collection_name: ClassVar[str] = "coming_soon_subscribers"

    email: EmailStr = Field(..., description="Subscriber email (unique).")


__all__ = ["ComingSoonSubscriberDocument"]
