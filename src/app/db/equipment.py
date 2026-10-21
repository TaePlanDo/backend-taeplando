"""Database queries for equipment types visible to a trainer."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogs import Equipment
from app.models.enums import CatalogVisibility


class EquipmentPage(NamedTuple):
    """One equipment page and the total number of matching entries."""

    items: list[Equipment]
    total: int


def _visible_to_trainer(trainer_id: UUID) -> ColumnElement[bool]:
    """Return the condition for global and trainer-owned equipment."""
    return or_(
        Equipment.visibility == CatalogVisibility.GLOBAL,
        Equipment.owner_user_id == trainer_id,
    )


async def list_visible_to_trainer(
    session: AsyncSession, trainer_id: UUID, *, offset: int, limit: int
) -> EquipmentPage:
    """Return one alphabetically ordered page of visible equipment types."""
    visibility_filter = _visible_to_trainer(trainer_id)
    statement = (
        select(Equipment, func.count().over())
        .where(visibility_filter)
        .order_by(Equipment.name, Equipment.id)
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(statement)
    rows = result.all()
    if rows:
        return EquipmentPage(
            items=[equipment for equipment, _ in rows], total=rows[0][1]
        )
    if offset == 0:
        return EquipmentPage(items=[], total=0)
    return EquipmentPage(
        items=[], total=await _count_visible_to_trainer(session, visibility_filter)
    )


async def _count_visible_to_trainer(
    session: AsyncSession, visibility_filter: ColumnElement[bool]
) -> int:
    """Count equipment entries visible to one trainer."""
    result = await session.execute(
        select(func.count()).select_from(Equipment).where(visibility_filter)
    )
    return result.scalar_one()


def create_for_trainer(trainer_id: UUID, name: str) -> Equipment:
    """Build a local equipment type owned by one trainer."""
    return Equipment(
        owner_user_id=trainer_id,
        name=name,
        visibility=CatalogVisibility.LOCAL,
    )
