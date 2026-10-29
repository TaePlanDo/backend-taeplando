"""Authenticated API for global and trainer-owned exercises."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exercise_list_filters import get_exercise_list_filters
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.exercise_list_filters import ExerciseListFilters
from app.schemas.exercises import ExerciseResponse, ExerciseUpdate, ExerciseWrite
from app.services import exercise_service

router = APIRouter(prefix="/exercises", tags=["exercises"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]
ExerciseFilters = Annotated[ExerciseListFilters, Depends(get_exercise_list_filters)]


def _not_found() -> HTTPException:
    """Use one response for missing and foreign-owned private exercises."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found"
    )


def _invalid_configuration() -> HTTPException:
    """Avoid disclosing whether an unavailable catalog entry exists."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Exercise configuration contains unavailable catalog entries",
    )


@router.get("", response_model=PaginatedResponse[ExerciseResponse])
async def list_exercises(
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: ExerciseFilters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[ExerciseResponse]:
    """List one page of global catalog and trainer-owned exercises."""
    return await exercise_service.list_exercises(
        session,
        current_trainer.id,
        filters=filters,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
async def create_exercise(
    payload: ExerciseWrite,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ExerciseResponse:
    """Create an active private exercise owned by the authenticated trainer."""
    try:
        return await exercise_service.create_exercise(
            session, current_trainer.id, payload
        )
    except exercise_service.InvalidExerciseConfigurationError as exc:
        raise _invalid_configuration() from exc


@router.put("/{exercise_id}", response_model=ExerciseResponse)
async def update_exercise(
    exercise_id: UUID,
    payload: ExerciseUpdate,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ExerciseResponse:
    """Replace editable fields of a private exercise owned by the trainer."""
    try:
        return await exercise_service.update_exercise(
            session, current_trainer.id, exercise_id, payload
        )
    except exercise_service.ExerciseNotFoundError as exc:
        raise _not_found() from exc
    except exercise_service.InvalidExerciseConfigurationError as exc:
        raise _invalid_configuration() from exc


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise(
    exercise_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Mark a trainer-owned private exercise inactive without deleting history."""
    try:
        await exercise_service.delete_exercise(session, current_trainer.id, exercise_id)
    except exercise_service.ExerciseNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
