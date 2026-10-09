from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def require_database_url(self) -> str:
        """Return the database URL or raise an error when it is missing."""

        if self.database_url is None:
            message = "DATABASE_URL must be configured before connecting to the database."
            raise RuntimeError(message)

        return self.database_url


@lru_cache
def get_settings() -> Settings:
    """Create and cache application settings for the process lifetime."""

    return Settings()
