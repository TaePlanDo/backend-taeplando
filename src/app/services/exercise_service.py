"""Business operations for the exercise catalog."""

import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.schemas.common import PaginatedResponse
from app.schemas.exercises import ExerciseResponse, ExerciseWrite


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
        duration_minutes=payload.duration_minutes,
    )
    session.add_all((exercise, trainer_exercise))
    await session.commit()
    return ExerciseResponse(
        id=exercise.id,
        owner_user_id=exercise.owner_user_id,
        scope=exercise.scope,
        name=exercise.name,
        description=exercise.description,
        duration_minutes=trainer_exercise.duration_minutes,
        status=trainer_exercise.status,
    )


def _to_response(exercise: exercises_db.ListedExercise) -> ExerciseResponse:
    """Map a normalized database row to the public exercise representation."""
    return ExerciseResponse(
        id=exercise.id,
        owner_user_id=exercise.owner_user_id,
        scope=exercise.scope,
        name=exercise.name,
        description=exercise.description,
        duration_minutes=exercise.duration_minutes,
        status=exercise.status,
    )
