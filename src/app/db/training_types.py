"""Database queries for training types visible to a trainer."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogs import TrainingType
from app.models.enums import CatalogVisibility


class TrainingTypePage(NamedTuple):
    """One training-type page and the total number of matching entries."""

    items: list[TrainingType]
    total: int


def _visible_to_trainer(trainer_id: UUID) -> ColumnElement[bool]:
    """Return the condition for global and trainer-owned training types."""
    return or_(
        TrainingType.visibility == CatalogVisibility.GLOBAL,
        TrainingType.owner_user_id == trainer_id,
    )


async def list_visible_to_trainer(
    session: AsyncSession, trainer_id: UUID, *, offset: int, limit: int
) -> TrainingTypePage:
    """Return one alphabetically ordered page of visible training types."""
    visibility_filter = _visible_to_trainer(trainer_id)
    statement = (
        select(TrainingType, func.count().over())
        .where(visibility_filter)
        .order_by(TrainingType.name, TrainingType.id)
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(statement)
    rows = result.all()
    if rows:
        return TrainingTypePage(
            items=[training_type for training_type, _ in rows], total=rows[0][1]
        )
    if offset == 0:
        return TrainingTypePage(items=[], total=0)
    return TrainingTypePage(
        items=[], total=await _count_visible_to_trainer(session, visibility_filter)
    )


async def _count_visible_to_trainer(
    session: AsyncSession, visibility_filter: ColumnElement[bool]
) -> int:
    """Count training types visible to one trainer."""
    result = await session.execute(
        select(func.count()).select_from(TrainingType).where(visibility_filter)
    )
    return result.scalar_one()
