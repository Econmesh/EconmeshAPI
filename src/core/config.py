"""Application configuration.

Uses pydantic-settings to load values from environment variables and `.env`.
All access goes through ``get_settings()``, which is memoised via ``lru_cache``
to provide a thread-safe singleton.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    """Strongly-typed application settings, populated from env vars / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ----------------------------------------------------------
    ENV: Environment = Environment.DEVELOPMENT
    APP_NAME: str = "econmesh-api"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    ENABLE_DOCS: bool = True

    # --- Server ---------------------------------------------------------------
    HOST: str = "0.0.0.0"  # noqa: S104 — intentional in containerised contexts
    PORT: int = 8000
    REQUEST_TIMEOUT_SECONDS: int = 30

    # --- Logging --------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    # --- Security -------------------------------------------------------------
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    TRUSTED_HOSTS: list[str] = Field(default_factory=lambda: ["*"])
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # --- MongoDB --------------------------------------------------------------
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "econmesh"
    MONGO_MIN_POOL_SIZE: int = 10
    MONGO_MAX_POOL_SIZE: int = 100
    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = 5_000

    # --- Redis ----------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    SESSION_TTL_SECONDS: int = 3_600

    # --- Firebase -------------------------------------------------------------
    # One of the two MUST be provided in non-test environments.
    FIREBASE_CREDENTIALS_PATH: Path | None = None
    FIREBASE_CREDENTIALS_JSON: str | None = None
    FIREBASE_PROJECT_ID: str | None = None
    FIREBASE_STORAGE_BUCKET: str | None = None
    # Tolerate small clock drift between this host and Google/Firebase (seconds).
    FIREBASE_CLOCK_SKEW_SECONDS: int = 60

    # --- E-mail / SMTP --------------------------------------------------------
    # When MAIL_ENABLED is false the API still issues confirmation tokens but
    # does not attempt to send any email (useful for local dev / tests).
    MAIL_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True  # STARTTLS (port 587). Mutually exclusive with SSL.
    SMTP_USE_SSL: bool = False  # Implicit TLS (port 465).
    SMTP_TIMEOUT_SECONDS: int = 10
    MAIL_FROM: str = "no-reply@econmesh.com"
    MAIL_FROM_NAME: str = "Econmesh"
    # Base URL the confirmation link points to (frontend route that reads the
    # ``token`` query param and calls ``POST /auth/verify``).
    FRONTEND_VERIFY_URL: str = "https://app.econmesh.com/verify"

    # ------------------------------------------------------------------ helpers
    @field_validator("FIREBASE_CLOCK_SKEW_SECONDS")
    @classmethod
    def _validate_firebase_clock_skew(cls, v: int) -> int:
        if v < 0 or v > 60:
            raise ValueError("FIREBASE_CLOCK_SKEW_SECONDS must be between 0 and 60.")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalised = v.upper()
        if normalised not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return normalised

    @model_validator(mode="after")
    def _validate_mail(self) -> Settings:
        if self.SMTP_USE_TLS and self.SMTP_USE_SSL:
            raise ValueError("SMTP_USE_TLS and SMTP_USE_SSL are mutually exclusive.")
        if self.MAIL_ENABLED and not self.SMTP_HOST:
            raise ValueError("SMTP_HOST is required when MAIL_ENABLED is true.")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENV is Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.ENV is Environment.DEVELOPMENT

    @property
    def is_test(self) -> bool:
        return self.ENV is Environment.TEST

    @property
    def docs_url(self) -> str | None:
        return "/docs" if self.ENABLE_DOCS else None

    @property
    def redoc_url(self) -> str | None:
        return "/redoc" if self.ENABLE_DOCS else None

    @property
    def openapi_url(self) -> str | None:
        return f"{self.API_V1_PREFIX}/openapi.json" if self.ENABLE_DOCS else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
