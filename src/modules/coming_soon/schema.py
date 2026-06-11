"""DTOs for the ``coming_soon`` module."""

from __future__ import annotations

from pydantic import EmailStr, Field

from src.shared.schemas.base import APIModel


class ComingSoonSubscribeRequest(APIModel):
    email: EmailStr = Field(..., description="Email to notify when the product launches.")


__all__ = ["ComingSoonSubscribeRequest"]
