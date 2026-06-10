"""DTOs for the ``users`` module."""

from __future__ import annotations

import re
from datetime import date, datetime
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from src.shared.schemas.base import APIModel


class ProfileAddressInput(APIModel):
    postal_code: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class ProfileAddressResponse(APIModel):
    postal_code: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


def _strip_non_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _is_valid_cpf(cpf: str) -> bool:
    digits = _strip_non_digits(cpf)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False

    def _calc_check(slice_len: int) -> int:
        nums = [int(d) for d in digits[:slice_len]]
        weights = list(range(slice_len + 1, 1, -1))
        total = sum(n * w for n, w in zip(nums, weights, strict=True))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    return _calc_check(9) == int(digits[9]) and _calc_check(10) == int(digits[10])


class UserProfileUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    cpf: str | None = Field(default=None, min_length=11, max_length=14)
    birth_date: date | None = None
    job_title: str | None = Field(default=None, max_length=120)
    address: ProfileAddressInput | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    picture_storage_key: str | None = Field(default=None, max_length=500)
    picture_url: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("name must not be blank")
        return value.strip() if value is not None else None

    @field_validator("cpf")
    @classmethod
    def _validate_cpf(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = _strip_non_digits(value)
        if not _is_valid_cpf(digits):
            raise ValueError("Invalid CPF.")
        return digits


class UserProfileResponse(APIModel):
    id: UUID
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    picture: str | None = None
    picture_storage_key: str | None = None
    cpf: str | None = None
    birth_date: date | None = None
    job_title: str | None = None
    address: ProfileAddressResponse | None = None
    country: str
    is_complete: bool
    created_at: datetime
    updated_at: datetime


class AvatarPresignRequest(APIModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=3, max_length=100)


class AvatarPresignResponse(APIModel):
    upload_url: str
    storage_key: str
    public_url: str
    expires_at: datetime


__all__ = [
    "AvatarPresignRequest",
    "AvatarPresignResponse",
    "ProfileAddressInput",
    "ProfileAddressResponse",
    "UserProfileResponse",
    "UserProfileUpdate",
]
