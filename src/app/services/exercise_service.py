"""Business operations for the exercise catalog."""

import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.models.enums import TrainerExerciseStatus
from app.models.exercises import Exercise, TrainerExercise
from app.schemas.common import PaginatedResponse
from app.schemas.exercises import ExerciseResponse, ExerciseUpdate, ExerciseWrite


class ExerciseNotFoundError(Exception):
    """Raised when a private exercise is absent or owned by another trainer."""


async def list_exercises(
    session: AsyncSession, trainer_id: UUID, *, page: int, page_size: int
) -> PaginatedResponse[ExerciseResponse]:
    """Return one page of global and trainer-owned exercises."""
    db_page = await exercises_db.list_available_to_trainer(
        session,
        trainer_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return PaginatedResponse(
        items=[_to_response(listed_exercise) for listed_exercise in db_page.items],
        total=db_page.total,
        page=page if db_page.total else 1,
        page_size=page_size,
        total_pages=max(1, math.ceil(db_page.total / page_size)),
    )


async def create_exercise(
    session: AsyncSession, trainer_id: UUID, payload: ExerciseWrite
) -> ExerciseResponse:
    """Create an active private exercise owned by the authenticated trainer."""
    exercise, trainer_exercise = exercises_db.create_for_trainer(
        trainer_id,
        name=payload.name,
        description=payload.description,
        image_url=str(payload.image_url) if payload.image_url else None,
        min_age=payload.min_age,
        max_age=payload.max_age,
        min_participants=payload.min_participants,
        max_participants=payload.max_participants,
        duration_minutes=payload.duration_minutes,
    )
    session.add_all((exercise, trainer_exercise))
    await session.commit()
    return _to_response_from_models(exercise, trainer_exercise)


async def update_exercise(
    session: AsyncSession,
    trainer_id: UUID,
    exercise_id: UUID,
    payload: ExerciseUpdate,
) -> ExerciseResponse:
    """Replace the editable fields of one trainer-owned private exercise."""
    exercise, trainer_exercise = await _get_owned_private_exercise_or_raise(
        session, trainer_id, exercise_id
    )
    exercise.name = payload.name
    exercise.description = payload.description
    exercise.image_url = str(payload.image_url) if payload.image_url else None
    trainer_exercise.duration_minutes = payload.duration_minutes
    await session.commit()
    return _to_response_from_models(exercise, trainer_exercise)


async def delete_exercise(
    session: AsyncSession, trainer_id: UUID, exercise_id: UUID
) -> None:
    """Make a trainer-owned private exercise unavailable without deleting history."""
    _, trainer_exercise = await _get_owned_private_exercise_or_raise(
        session, trainer_id, exercise_id
    )
    trainer_exercise.status = TrainerExerciseStatus.INACTIVE
    await session.commit()


def _to_response(exercise: exercises_db.ListedExercise) -> ExerciseResponse:
    """Map a normalized database row to the public exercise representation."""
    return ExerciseResponse(
        id=exercise.id,
        owner_user_id=exercise.owner_user_id,
        scope=exercise.scope,
        name=exercise.name,
        description=exercise.description,
        image_url=exercise.image_url,
        min_age=exercise.min_age,
        max_age=exercise.max_age,
        min_participants=exercise.min_participants,
        max_participants=exercise.max_participants,
        duration_minutes=exercise.duration_minutes,
        status=exercise.status,
    )


async def _get_owned_private_exercise_or_raise(
    session: AsyncSession, trainer_id: UUID, exercise_id: UUID
) -> tuple[Exercise, TrainerExercise]:
    """Return an owned private exercise or keep foreign records undiscoverable."""
    exercise_and_configuration = await exercises_db.get_private_for_trainer(
        session, trainer_id, exercise_id
    )
    if exercise_and_configuration is None:
        raise ExerciseNotFoundError
    return exercise_and_configuration


def _to_response_from_models(
    exercise: Exercise, trainer_exercise: TrainerExercise
) -> ExerciseResponse:
    """Map an owned private exercise and its configuration to the API contract."""
    return ExerciseResponse(
        id=exercise.id,
        owner_user_id=exercise.owner_user_id,
        scope=exercise.scope,
        name=exercise.name,
        description=exercise.description,
        image_url=exercise.image_url,
        min_age=trainer_exercise.min_age,
        max_age=trainer_exercise.max_age,
        min_participants=trainer_exercise.min_participants,
        max_participants=trainer_exercise.max_participants,
        duration_minutes=trainer_exercise.duration_minutes,
        status=trainer_exercise.status,
    )
