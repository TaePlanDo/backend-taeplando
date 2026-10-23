"""Authenticated API for the training-type catalog."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.training_types import TrainingTypeResponse
from app.services import training_type_service

router = APIRouter(prefix="/training-types", tags=["training-types"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=PaginatedResponse[TrainingTypeResponse])
async def list_training_types(
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[TrainingTypeResponse]:
    """List training types visible to the authenticated trainer."""
    return await training_type_service.list_training_types(
        session, current_trainer.id, page=page, page_size=page_size
    )
