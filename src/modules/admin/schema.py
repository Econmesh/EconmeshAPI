"""DTOs for the ``admin`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from src.modules.auth.schema import AdminRegisterRequest, MeResponse
from src.modules.companies.schema import CompanyCreate, CompanyResponse, CompanyUpdate
from src.modules.opportunities.schema import OpportunityListResponse, OpportunityResponse
from src.shared.constants.roles import Role
from src.shared.schemas.base import APIModel


class AdminUserListParams(APIModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    role: Role | None = None
    is_active: bool | None = None
    email: str | None = Field(default=None, max_length=254)


class AdminUserListItem(APIModel):
    id: UUID
    firebase_uid: str
    email: EmailStr | None = None
    name: str | None = None
    phone: str | None = None
    role: Role
    is_active: bool
    is_verified: bool
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class AdminUserListResponse(APIModel):
    items: list[AdminUserListItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class AdminUserUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    role: Role | None = None
    is_active: bool | None = None


class AdminCompanyCreate(CompanyCreate):
    owner_user_id: UUID = Field(..., description="User who owns this company.")


class AdminCompanyListResponse(APIModel):
    items: list[CompanyResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


__all__ = [
    "AdminCompanyCreate",
    "AdminCompanyListResponse",
    "AdminRegisterRequest",
    "AdminUserListItem",
    "AdminUserListParams",
    "AdminUserListResponse",
    "AdminUserUpdate",
    "CompanyResponse",
    "CompanyUpdate",
    "MeResponse",
    "OpportunityListResponse",
    "OpportunityResponse",
]
