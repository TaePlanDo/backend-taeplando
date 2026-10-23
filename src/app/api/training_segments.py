"""Authenticated API for the fixed training-segment catalog."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.training_segments import TrainingSegmentResponse
from app.services import training_segment_service

router = APIRouter(prefix="/training-segments", tags=["training-segments"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=list[TrainingSegmentResponse])
async def list_segments(
    _current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[TrainingSegmentResponse]:
    """List seeded training segments available for group schema editing."""
    return await training_segment_service.list_segments(session)
