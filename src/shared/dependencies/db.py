"""FastAPI dependencies that expose the MongoDB connection to routes/services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.database import mongo

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


def get_db() -> AsyncDatabase:
    """Return the active Mongo database. Raises if not initialised."""
    return mongo.db


def get_collection(name: str):  # noqa: ANN201 — typed via TYPE_CHECKING
    """Closure-style accessor: ``Depends(get_collection_factory("users"))``."""
    return mongo.get_collection(name)


def get_collection_factory(name: str):  # noqa: ANN201
    """Build a dependency callable that yields a specific collection."""

    def _dep() -> AsyncCollection:
        return mongo.get_collection(name)

    return _dep


__all__ = ["get_collection", "get_collection_factory", "get_db"]
