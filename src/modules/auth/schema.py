"""DTOs exchanged over HTTP for the ``auth`` module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, field_validator, model_validator

from src.modules.companies.schema import CompanyAddressInput
from src.shared.constants.roles import Role
from src.shared.schemas.base import APIModel

# Firebase enforces a 6-char minimum on passwords; we ask for a bit more.
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 128


class LoginRequest(APIModel):
    """Body for ``POST /auth/login`` — clients hand over the Firebase ID token."""

    id_token: str = Field(..., min_length=20, description="Firebase-issued ID token.")


class RegisterCompanyInput(APIModel):
    """Company data collected at self-service signup (steps 1–2)."""

    legal_name: str = Field(..., min_length=2, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    tax_id: str = Field(..., min_length=14, max_length=20, description="CNPJ digits only.")
    email: EmailStr
    phone: str = Field(..., min_length=8, max_length=30)
    address: CompanyAddressInput
    country: str = Field(default="BR", min_length=2, max_length=2)

    @field_validator("legal_name")
    @classmethod
    def _legal_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("legal_name must not be blank")
        return v.strip()

    @field_validator("trade_name")
    @classmethod
    def _empty_trade_name_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None

    @field_validator("tax_id")
    @classmethod
    def _digits_only_tax_id(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 14:
            raise ValueError("tax_id must be a 14-digit CNPJ")
        return digits

    @field_validator("phone")
    @classmethod
    def _phone_not_blank(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) < 8:
            raise ValueError("phone must contain at least 8 digits")
        return v.strip()

    @model_validator(mode="after")
    def _address_required_fields(self) -> RegisterCompanyInput:
        address = self.address
        missing: list[str] = []
        if not (address.postal_code or "").strip():
            missing.append("postal_code")
        if not (address.street or "").strip():
            missing.append("street")
        if not (address.number or "").strip():
            missing.append("number")
        if not (address.city or "").strip():
            missing.append("city")
        if not (address.state or "").strip():
            missing.append("state")
        if missing:
            raise ValueError(f"address requires {', '.join(missing)}")
        return self


class RegisterRequest(APIModel):
    """Body for ``POST /auth/register`` — self-service signup of a standard user."""

    full_name: str = Field(..., min_length=2, max_length=120, description="User's full name.")
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32, description="Optional phone number.")
    password: str = Field(..., min_length=_PASSWORD_MIN_LENGTH, max_length=_PASSWORD_MAX_LENGTH)
    # Optional: the frontend already compares the two fields. When sent, we
    # re-validate server-side as defense-in-depth.
    password_confirm: str | None = Field(default=None)
    company: RegisterCompanyInput

    @field_validator("full_name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("full_name must not be blank")
        return v

    @model_validator(mode="after")
    def _passwords_match(self) -> RegisterRequest:
        if self.password_confirm is not None and self.password != self.password_confirm:
            raise ValueError("password and password_confirm do not match")
        return self


class AdminRegisterRequest(RegisterRequest):
    """Body for ``POST /auth/admin/users`` — privileged creation by an admin.

    Lets an authenticated admin assign any role (defaults to ``admin``) and
    optionally skip the email-confirmation step. Company is not required.
    """

    company: RegisterCompanyInput | None = None
    role: Role = Field(default=Role.ADMIN, description="Role to grant the new user.")
    auto_confirm: bool = Field(
        default=True,
        description="When true, the account is created already confirmed (no email step).",
    )


class VerifyAccountRequest(APIModel):
    """Body for ``POST /auth/verify`` — confirms an account with its token."""

    token: str = Field(..., min_length=16, description="Raw confirmation token from the email.")


class ResendVerificationRequest(APIModel):
    """Body for ``POST /auth/resend-verification``."""

    email: EmailStr


class MeResponse(APIModel):
    """Identity envelope returned by ``GET /auth/me``."""

    id: UUID
    firebase_uid: str
    email: EmailStr | None = None
    name: str | None = None
    phone: str | None = None
    picture: str | None = None
    email_verified: bool = False
    is_verified: bool = False
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class RegisterResponse(APIModel):
    """Payload returned after a successful registration."""

    user: MeResponse
    message: str
    # Returned ONLY in non-production environments so the flow is testable
    # without a configured mail transport. Never exposed in production.
    verification_token: str | None = None


class TokenIntrospectionResponse(APIModel):
    """Diagnostics returned by ``POST /auth/login`` so a client can debug tokens."""

    uid: str
    issuer: str | None = None
    audience: str | None = None
    expires_at: int | None = Field(default=None, description="Unix epoch seconds.")
    issued_at: int | None = None
    email_verified: bool = False


class LoginResponse(APIModel):
    """Full payload for ``POST /auth/login``: identity + token diagnostics."""

    user: MeResponse
    token: TokenIntrospectionResponse


__all__ = [
    "AdminRegisterRequest",
    "LoginRequest",
    "LoginResponse",
    "MeResponse",
    "RegisterCompanyInput",
    "RegisterRequest",
    "RegisterResponse",
    "ResendVerificationRequest",
    "TokenIntrospectionResponse",
    "VerifyAccountRequest",
]
