"""Shared queries for trainer-visible equipment and training-type catalogs."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogs import CatalogEntryMixin
from app.models.enums import CatalogVisibility


class CatalogPage[Entry: CatalogEntryMixin](NamedTuple):
    """One page of entries from either trainer-visible catalog."""

    items: list[Entry]
    total: int


def _visible_to_trainer[Entry: CatalogEntryMixin](
    catalog: type[Entry], trainer_id: UUID
) -> ColumnElement[bool]:
    """Return the condition for global and trainer-owned catalog entries."""
    return or_(
        catalog.visibility == CatalogVisibility.GLOBAL,
        catalog.owner_user_id == trainer_id,
    )


async def list_visible_to_trainer[Entry: CatalogEntryMixin](
    session: AsyncSession,
    trainer_id: UUID,
    *,
    catalog: type[Entry],
    offset: int,
    limit: int,
) -> CatalogPage[Entry]:
    """Return one alphabetically ordered page of visible catalog entries."""
    visibility_filter = _visible_to_trainer(catalog, trainer_id)
    statement = (
        select(catalog, func.count().over())
        .where(visibility_filter)
        .order_by(catalog.name, catalog.id)
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(statement)
    rows = result.all()
    if rows:
        return CatalogPage(items=[entry for entry, _ in rows], total=rows[0][1])
    if offset == 0:
        return CatalogPage(items=[], total=0)
    return CatalogPage(
        items=[],
        total=await _count_visible_to_trainer(session, catalog, visibility_filter),
    )


async def list_visible_by_ids[Entry: CatalogEntryMixin](
    session: AsyncSession,
    trainer_id: UUID,
    *,
    catalog: type[Entry],
    ids: list[UUID],
) -> list[Entry]:
    """Return requested entries only when they are visible to the trainer."""
    if not ids:
        return []
    result = await session.scalars(
        select(catalog).where(
            catalog.id.in_(ids),
            _visible_to_trainer(catalog, trainer_id),
        )
    )
    return list(result)


async def _count_visible_to_trainer[Entry: CatalogEntryMixin](
    session: AsyncSession,
    catalog: type[Entry],
    visibility_filter: ColumnElement[bool],
) -> int:
    """Count entries visible to one trainer in one catalog."""
    result = await session.execute(
        select(func.count()).select_from(catalog).where(visibility_filter)
    )
    return result.scalar_one()
