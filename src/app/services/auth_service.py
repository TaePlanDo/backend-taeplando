from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expires_at,
    verify_password,
)
from app.db import refresh_tokens as refresh_tokens_db
from app.db import users as users_db
from app.models.users import User
from app.schemas.auth import TokenResponse, UserResponse


def user_to_response(user: User) -> UserResponse:
    """Map an ORM user to the public API shape."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        auth_method=user.auth_method,
    )


async def login(
    session: AsyncSession,
    email: str,
    password: str,
    settings: Settings,
) -> tuple[TokenResponse, str]:
    """Authenticate with email/password and issue a new token pair."""
    user = await users_db.get_user_by_email(session, email)
    if user is None or user.password_hash is None:
        raise AuthError("Invalid credentials")
    if not verify_password(password, user.password_hash):
        raise AuthError("Invalid credentials")
    return await create_auth_tokens(session, user.id, settings)


async def refresh(
    session: AsyncSession,
    refresh_token: str,
    settings: Settings,
) -> tuple[TokenResponse, str]:
    """Rotate a refresh token: consume the old one and issue a new pair."""
    token_hash = hash_refresh_token(refresh_token)
    record = await refresh_tokens_db.consume_refresh_token(session, token_hash)
    if record is None:
        raise AuthError("Invalid or expired refresh token")
    if record.expires_at < datetime.now(UTC):
        await session.commit()
        raise AuthError("Invalid or expired refresh token")

    return await create_auth_tokens(session, record.user_id, settings)


async def get_user_response(session: AsyncSession, user_id: UUID) -> UserResponse:
    """Load the user for `/auth/me`, or raise if missing."""
    user = await users_db.get_user_by_id(session, user_id)
    if user is None:
        raise AuthError("Not authenticated")
    return user_to_response(user)


async def create_auth_tokens(
    session: AsyncSession,
    user_id: UUID,
    settings: Settings,
) -> tuple[TokenResponse, str]:
    """Create an access JWT and a new persisted refresh token; commit once."""
    access_token, expires_in = create_access_token(user_id, settings)
    plain_refresh = generate_refresh_token()
    await refresh_tokens_db.create_refresh_token(
        session,
        user_id=user_id,
        token_hash=hash_refresh_token(plain_refresh),
        expires_at=refresh_token_expires_at(settings),
    )
    await session.commit()
    return (
        TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
        ),
        plain_refresh,
    )
