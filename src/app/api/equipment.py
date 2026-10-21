"""Authenticated API for training equipment types."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.equipment import EquipmentResponse, EquipmentWrite
from app.services import equipment_service

router = APIRouter(prefix="/equipment", tags=["equipment"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]


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
