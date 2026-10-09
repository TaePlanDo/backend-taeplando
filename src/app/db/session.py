from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Create and cache the asynchronous PostgreSQL engine."""

    return create_async_engine(
        get_settings().require_database_url(),
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create and cache the factory used to open database sessions."""

    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide one database session to a FastAPI request."""

    async with get_session_factory()() as session:
        yield session


async def check_database_connection() -> None:
    """Verify that the configured database accepts a simple query."""

    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    """Close open database connections during application shutdown."""

    if get_engine.cache_info().currsize == 0:
        return

    await get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
