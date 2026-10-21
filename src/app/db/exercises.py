"""Database queries for global and trainer-owned exercises."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExerciseScope, ExerciseVersionStatus, TrainerExerciseStatus
from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise


class ListedExercise(NamedTuple):
    """Exercise data from either the global catalog or a trainer's own set."""

    exercise: Exercise
    trainer_exercise: TrainerExercise | None
    approved_version: ExerciseVersion | None


class ExercisePage(NamedTuple):
    """One page of exercises and the total number visible to a trainer."""

    items: list[ListedExercise]
    total: int


def _visible_query(
    trainer_id: UUID,
) -> Select[Exercise, TrainerExercise, ExerciseVersion]:
    """Build the shared catalog-and-private-exercise query for one trainer."""
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
    return (
        select(Exercise, TrainerExercise, ExerciseVersion)
        .outerjoin(TrainerExercise, trainer_exercise_join)
        .outerjoin(ExerciseVersion, approved_version_join)
        .where(or_(private_exercise, global_exercise))
    )


async def list_available_to_trainer(
    session: AsyncSession, trainer_id: UUID, *, offset: int, limit: int
) -> ExercisePage:
    """Return one alphabetically ordered page of available exercises."""
    visible_query = _visible_query(trainer_id)
    result = await session.execute(
        visible_query.add_columns(func.count().over())
        .order_by(Exercise.name, Exercise.id)
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()
    if rows:
        return ExercisePage(
            items=[ListedExercise(*row[:3]) for row in rows], total=rows[0][3]
        )
    if offset == 0:
        return ExercisePage(items=[], total=0)

    total_result = await session.execute(
        select(func.count()).select_from(
            visible_query.with_only_columns(Exercise.id).subquery()
        )
    )
    return ExercisePage(items=[], total=total_result.scalar_one())


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
