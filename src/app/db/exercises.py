"""Database queries for global and trainer-owned exercises."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExerciseScope, ExerciseVersionStatus, TrainerExerciseStatus
from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise


class ListedExercise(NamedTuple):
    """Exercise data from either the global catalog or a trainer's own set."""

    exercise: Exercise
    trainer_exercise: TrainerExercise | None
    approved_version: ExerciseVersion | None


async def list_available_to_trainer(
    session: AsyncSession, trainer_id: UUID
) -> list[ListedExercise]:
    """Return alphabetically ordered global and trainer-owned exercises."""
    trainer_exercise_join = and_(
        TrainerExercise.exercise_id == Exercise.id,
        TrainerExercise.trainer_id == trainer_id,
    )
    approved_version_join = ExerciseVersion.id == Exercise.latest_approved_version_id
    private_exercise = and_(
        Exercise.scope == ExerciseScope.PRIVATE,
        Exercise.owner_user_id == trainer_id,
        TrainerExercise.id.is_not(None),
    )
    global_exercise = and_(
        Exercise.scope == ExerciseScope.GLOBAL,
        ExerciseVersion.status == ExerciseVersionStatus.APPROVED,
    )
    result = await session.execute(
        select(Exercise, TrainerExercise, ExerciseVersion)
        .outerjoin(TrainerExercise, trainer_exercise_join)
        .outerjoin(ExerciseVersion, approved_version_join)
        .where(or_(private_exercise, global_exercise))
        .order_by(Exercise.name, Exercise.id)
    )
    return [ListedExercise(*row) for row in result.all()]


def create_for_trainer(
    trainer_id: UUID, *, name: str, description: str, duration_minutes: int
) -> tuple[Exercise, TrainerExercise]:
    """Build a private exercise and its active trainer configuration."""
    exercise = Exercise(
        owner_user_id=trainer_id,
        scope=ExerciseScope.PRIVATE,
        name=name,
        description=description,
    )
    trainer_exercise = TrainerExercise(
        trainer_id=trainer_id,
        exercise=exercise,
        status=TrainerExerciseStatus.ACTIVE,
        min_age=1,
        max_age=99,
        min_participants=1,
        max_participants=99,
        duration_minutes=duration_minutes,
    )
    return exercise, trainer_exercise
