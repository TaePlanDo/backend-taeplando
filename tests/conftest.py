from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import app


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
