from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-change-in-production-min-32-chars!!"
_DEV_SESSION_SECRET = "dev-session-secret-change-in-prod-min-32!!"


class AppEnvironment(StrEnum):
    """Runtime environment used for production-only checks."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = None

    environment: AppEnvironment = AppEnvironment.DEVELOPMENT

    jwt_secret: str = Field(default=_DEV_JWT_SECRET, min_length=32)
    session_secret: str = Field(default=_DEV_SESSION_SECRET, min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    refresh_cookie_name: str = "refresh_token"
    # Sent on /api/auth/* via Vite proxy (refresh + logout).
    refresh_cookie_path: str = "/api/auth"
    refresh_cookie_secure: bool = False

    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    def require_database_url(self) -> str:
        """Return the database URL or raise when it is missing."""
        if self.database_url is None:
            raise RuntimeError(
                "DATABASE_URL must be configured before connecting to the database."
            )
        return self.database_url

    @field_validator("cors_origins")
    @classmethod
    def strip_cors_origins(cls, value: str) -> str:
        """Trim surrounding whitespace from the raw CORS origins string."""
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse `cors_origins` into a list of non-empty origin URLs."""
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    @model_validator(mode="after")
    def require_strong_secrets_in_production(self) -> "Settings":
        """Reject default/weak secrets when `environment` is production."""
        if self.environment != AppEnvironment.PRODUCTION:
            return self
        if self.jwt_secret == _DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set in production")
        if self.session_secret == _DEV_SESSION_SECRET:
            raise ValueError("SESSION_SECRET must be set in production")
        if not self.refresh_cookie_secure:
            raise ValueError("REFRESH_COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
