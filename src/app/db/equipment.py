"""Database helpers for trainer-owned equipment."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogs import Equipment
from app.models.enums import CatalogVisibility


async def get_local_for_trainer(
    session: AsyncSession, trainer_id: UUID, equipment_id: UUID
) -> Equipment | None:
    """Find one trainer-owned local equipment type."""
    result = await session.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.owner_user_id == trainer_id,
            Equipment.visibility == CatalogVisibility.LOCAL,
        )
    )
    return result.scalar_one_or_none()


def create_for_trainer(trainer_id: UUID, name: str) -> Equipment:
    """Build a local equipment type owned by one trainer."""
    return Equipment(
        owner_user_id=trainer_id,
        name=name,
        visibility=CatalogVisibility.LOCAL,
    )
