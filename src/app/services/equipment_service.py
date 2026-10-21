"""Business operations for training equipment types."""

import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import equipment as equipment_db
from app.models.catalogs import Equipment
from app.schemas.common import PaginatedResponse
from app.schemas.equipment import EquipmentResponse, EquipmentWrite


async def list_equipment(
    session: AsyncSession, trainer_id: UUID, *, page: int, page_size: int
) -> PaginatedResponse[EquipmentResponse]:
    """Return one page of equipment types visible to a trainer."""
    db_page = await equipment_db.list_visible_to_trainer(
        session,
        trainer_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return PaginatedResponse(
        items=[_to_response(equipment) for equipment in db_page.items],
        total=db_page.total,
        page=page if db_page.total else 1,
        page_size=page_size,
        total_pages=max(1, math.ceil(db_page.total / page_size)),
    )


async def create_equipment(
    session: AsyncSession, trainer_id: UUID, payload: EquipmentWrite
) -> EquipmentResponse:
    """Create a trainer-owned local equipment type."""
    equipment = equipment_db.create_for_trainer(trainer_id, payload.name)
    session.add(equipment)
    await session.commit()
    return _to_response(equipment)


def _to_response(equipment: Equipment) -> EquipmentResponse:
    """Map an equipment ORM object to the API response shape."""
    return EquipmentResponse(
        id=equipment.id,
        name=equipment.name,
        visibility=equipment.visibility,
        created_at=equipment.created_at,
    )
