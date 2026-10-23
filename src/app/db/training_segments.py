"""Database queries for the fixed training-segment catalog."""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogs import TrainingSegment


async def get_by_code(session: AsyncSession, code: str) -> TrainingSegment | None:
    """Return one fixed training-schema segment by its immutable code."""
    result = await session.execute(
        select(TrainingSegment).where(TrainingSegment.code == code)
    )
    return result.scalar_one_or_none()


async def list_by_ids(
    session: AsyncSession, ids: Collection[int]
) -> list[TrainingSegment]:
    """Return the catalog segments that match the given identifiers."""
    if not ids:
        return []
    result = await session.execute(
        select(TrainingSegment).where(TrainingSegment.id.in_(ids))
    )
    return list(result.scalars().all())


async def list_all(session: AsyncSession) -> list[TrainingSegment]:
    """Return the full seeded training-segment catalog ordered by id."""
    result = await session.execute(select(TrainingSegment).order_by(TrainingSegment.id))
    return list(result.scalars().all())
