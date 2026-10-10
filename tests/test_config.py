import pytest
from pydantic import ValidationError

from app.core.config import AppEnvironment, Settings


def test_production_rejects_default_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment=AppEnvironment.PRODUCTION,
            jwt_secret="dev-only-change-in-production-min-32-chars!!",
            session_secret="dev-session-secret-change-in-prod-min-32!!",
            refresh_cookie_secure=True,
        )


def test_default_refresh_cookie_path_matches_vite_proxy() -> None:
    settings = Settings()
    assert settings.refresh_cookie_path == "/api/auth"
