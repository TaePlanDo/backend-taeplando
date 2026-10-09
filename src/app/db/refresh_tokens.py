from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import RefreshToken


async def create_refresh_token(
    session: AsyncSession,
    *,
    user_id: UUID,
    token_hash: str,
    expires_at: datetime,
) -> None:
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await session.flush()


async def get_refresh_token_by_hash(
    session: AsyncSession, token_hash: str
) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(session: AsyncSession, token_hash: str) -> None:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return
    await session.delete(row)
    await session.flush()
