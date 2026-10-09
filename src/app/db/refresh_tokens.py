from datetime import datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import RefreshToken


async def create_refresh_token(
    session: AsyncSession,
    *,
    user_id: UUID,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """Persist a hashed refresh token for the given user."""
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await session.flush()


async def consume_refresh_token(
    session: AsyncSession, token_hash: str
) -> RefreshToken | None:
    """Delete the refresh token by hash and return it, or None if missing.

    Uses a single DELETE … RETURNING so concurrent refreshes cannot both
    consume the same token.
    """
    result = await session.execute(
        delete(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .returning(RefreshToken)
    )
    record = result.scalar_one_or_none()
    if record is not None:
        await session.flush()
    return record
