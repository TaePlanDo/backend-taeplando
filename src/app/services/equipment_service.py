"""Business operations for training equipment types."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import catalogs as catalogs_db
from app.db import equipment as equipment_db
from app.models.catalogs import Equipment
from app.schemas.common import PaginatedResponse, paginate
from app.schemas.equipment import EquipmentResponse, EquipmentWrite


class EquipmentNotFoundError(Exception):
    """Raised when local equipment is absent or belongs to another trainer."""


async def list_equipment(
    session: AsyncSession, trainer_id: UUID, *, page: int, page_size: int
) -> PaginatedResponse[EquipmentResponse]:
    """Return one page of equipment types visible to a trainer."""
    db_page = await catalogs_db.list_visible_to_trainer(
        session,
        trainer_id,
        catalog=Equipment,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return paginate(
        items=[_to_response(equipment) for equipment in db_page.items],
        total=db_page.total,
        page=page,
        page_size=page_size,
    )


async def create_equipment(
    session: AsyncSession, trainer_id: UUID, payload: EquipmentWrite
) -> EquipmentResponse:
    """Create a trainer-owned local equipment type."""
    equipment = equipment_db.create_for_trainer(trainer_id, payload.name)
    session.add(equipment)
    await session.commit()
    return _to_response(equipment)


async def update_equipment(
    session: AsyncSession,
    trainer_id: UUID,
    equipment_id: UUID,
    payload: EquipmentWrite,
) -> EquipmentResponse:
    """Rename one trainer-owned local equipment type."""
    equipment = await _get_owned_local_equipment_or_raise(
        session, trainer_id, equipment_id
    )
    equipment.name = payload.name
    await session.commit()
    return _to_response(equipment)


async def delete_equipment(
    session: AsyncSession, trainer_id: UUID, equipment_id: UUID
) -> None:
    """Delete one trainer-owned local equipment type."""
    equipment = await _get_owned_local_equipment_or_raise(
        session, trainer_id, equipment_id
    )
    await session.delete(equipment)
    await session.commit()


async def _get_owned_local_equipment_or_raise(
    session: AsyncSession, trainer_id: UUID, equipment_id: UUID
) -> Equipment:
    """Return mutable equipment without revealing foreign or global entries."""
    equipment = await equipment_db.get_local_for_trainer(
        session, trainer_id, equipment_id
    )
    if equipment is None:
        raise EquipmentNotFoundError
    return equipment


def _to_response(equipment: Equipment) -> EquipmentResponse:
    """Map an equipment ORM object to the API response shape."""
    return EquipmentResponse(
        id=equipment.id,
        name=equipment.name,
        visibility=equipment.visibility,
        created_at=equipment.created_at,
    )
