"""Base Pydantic schemas reused across the application."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow


class APIModel(BaseModel):
    """Base for every DTO/schema that crosses the HTTP boundary."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
        extra="ignore",
    )


class DomainDocument(BaseModel):
    """Base for documents persisted to MongoDB.

    Conventions:
        * ``id`` is a public UUID, stored as the Mongo ``_id``.
        * Timestamps are always tz-aware UTC.
        * Subclasses set their own ``collection_name`` class var.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )

    collection_name: str = ""  # overridden per subclass — class-level constant

    id: UUID = Field(default_factory=new_uuid, alias="_id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def to_mongo(self) -> dict[str, Any]:
        """Serialise to a dict ready to be inserted into MongoDB."""
        return self.model_dump(by_alias=True, mode="python")

    def touch(self) -> None:
        """Refresh ``updated_at`` to ``now``."""
        self.updated_at = utcnow()


__all__ = ["APIModel", "DomainDocument"]
