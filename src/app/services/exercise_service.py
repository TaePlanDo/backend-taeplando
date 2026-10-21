"""Business operations for the exercise catalog."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.models.enums import ExerciseScope, TrainerExerciseStatus
from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise
from app.schemas.exercises import ExerciseResponse, ExerciseWrite


async def list_exercises(
    session: AsyncSession, trainer_id: UUID
) -> list[ExerciseResponse]:
    """List global catalog exercises and exercises owned by one trainer."""
    listed_exercises = await exercises_db.list_available_to_trainer(session, trainer_id)
    return [_to_response(*listed_exercise) for listed_exercise in listed_exercises]


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
    return _to_response(exercise, trainer_exercise, None)


def _to_response(
    exercise: Exercise,
    trainer_exercise: TrainerExercise | None,
    approved_version: ExerciseVersion | None,
) -> ExerciseResponse:
    """Map either source shape to the public exercise representation."""
    if exercise.scope == ExerciseScope.GLOBAL:
        if approved_version is None:
            raise RuntimeError("Global exercise has no approved version")
        return ExerciseResponse(
            id=exercise.id,
            owner_user_id=exercise.owner_user_id,
            scope=exercise.scope,
            name=approved_version.name,
            description=approved_version.description,
            duration_minutes=approved_version.duration_minutes,
            status=TrainerExerciseStatus.ACTIVE,
        )

    if trainer_exercise is None:
        raise RuntimeError("Private exercise has no trainer configuration")
    return ExerciseResponse(
        id=exercise.id,
        owner_user_id=exercise.owner_user_id,
        scope=exercise.scope,
        name=exercise.name,
        description=exercise.description,
        duration_minutes=trainer_exercise.duration_minutes,
        status=trainer_exercise.status,
    )
