from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.enums import AuthMethod
from app.models.users import User
from constants import TRAINER_ID


@pytest.fixture
def authenticated_trainer() -> Iterator[None]:
    """Authenticate route tests without involving JWT parsing."""
    app.dependency_overrides[get_current_user] = lambda: User(
        id=TRAINER_ID,
        email="trainer@example.com",
        full_name="Trainer",
        auth_method=AuthMethod.LOCAL,
        password_hash="hash",
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jwt_secret="test-jwt-secret-at-least-32-bytes-long",
        session_secret="test-session-secret-at-least-32-bytes",
        refresh_cookie_path="/auth",
        refresh_cookie_secure=False,
        frontend_url="http://localhost:5173",
        google_client_id="",
        google_client_secret="",
    )


@pytest.fixture
def override_settings(test_settings: Settings) -> Iterator[Settings]:
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield test_settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def db_session() -> Iterator[AsyncMock]:
    """Avoid a real PostgreSQL connection in unit tests."""
    session = AsyncMock(spec=AsyncSession)

    async def fake_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    yield session
    app.dependency_overrides.pop(get_db, None)
