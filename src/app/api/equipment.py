"""Authenticated API for training equipment types."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.equipment import EquipmentResponse, EquipmentWrite
from app.services import equipment_service

router = APIRouter(prefix="/equipment", tags=["equipment"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]


def _not_found() -> HTTPException:
    """Use one response for missing, foreign, and global equipment."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
    )


@router.get("", response_model=PaginatedResponse[EquipmentResponse])
async def list_equipment(
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[EquipmentResponse]:
    """List equipment types visible to the authenticated trainer."""
    return await equipment_service.list_equipment(
        session, current_trainer.id, page=page, page_size=page_size
    )


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    payload: EquipmentWrite,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EquipmentResponse:
    """Create a local equipment type for the authenticated trainer."""
    return await equipment_service.create_equipment(
        session, current_trainer.id, payload
    )


@router.put("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: UUID,
    payload: EquipmentWrite,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EquipmentResponse:
    """Rename a local equipment type owned by the authenticated trainer."""
    try:
        return await equipment_service.update_equipment(
            session, current_trainer.id, equipment_id, payload
        )
    except equipment_service.EquipmentNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a local equipment type owned by the authenticated trainer."""
    try:
        await equipment_service.delete_equipment(
            session, current_trainer.id, equipment_id
        )
    except equipment_service.EquipmentNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
