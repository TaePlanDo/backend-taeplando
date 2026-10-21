"""Database queries for global and trainer-owned exercises."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExerciseScope, ExerciseVersionStatus, TrainerExerciseStatus
from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise


class ListedExercise(NamedTuple):
    """One normalized exercise row visible in a trainer's catalog."""

    id: UUID
    owner_user_id: UUID
    scope: ExerciseScope
    name: str
    description: str
    duration_minutes: int
    status: TrainerExerciseStatus


class ExercisePage(NamedTuple):
    """One page of exercises and the total number visible to a trainer."""

    items: list[ListedExercise]
    total: int


async def list_available_to_trainer(
    session: AsyncSession, trainer_id: UUID, *, offset: int, limit: int
) -> ExercisePage:
    """Return one alphabetically ordered page of available exercises."""
    private_exercises = (
        select(
            Exercise.id,
            Exercise.owner_user_id,
            Exercise.scope,
            Exercise.name,
            Exercise.description,
            TrainerExercise.duration_minutes,
            TrainerExercise.status,
        )
        .join(TrainerExercise)
        .where(
            Exercise.scope == ExerciseScope.PRIVATE,
            Exercise.owner_user_id == trainer_id,
            TrainerExercise.trainer_id == trainer_id,
        )
    )
    global_exercises = (
        select(
            Exercise.id,
            Exercise.owner_user_id,
            Exercise.scope,
            ExerciseVersion.name,
            ExerciseVersion.description,
            ExerciseVersion.duration_minutes,
            literal(
                TrainerExerciseStatus.ACTIVE,
                type_=TrainerExercise.__table__.c.status.type,
            ).label("status"),
        )
        .join(
            ExerciseVersion, ExerciseVersion.id == Exercise.latest_approved_version_id
        )
        .where(
            Exercise.scope == ExerciseScope.GLOBAL,
            ExerciseVersion.status == ExerciseVersionStatus.APPROVED,
        )
    )
    visible_exercises = union_all(private_exercises, global_exercises).subquery()
    result = await session.execute(
        select(*visible_exercises.c, func.count().over())
        .order_by(visible_exercises.c.name, visible_exercises.c.id)
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()
    if rows:
        return ExercisePage(
            items=[ListedExercise(*row[:7]) for row in rows], total=rows[0][7]
        )
    if offset == 0:
        return ExercisePage(items=[], total=0)

    total_result = await session.execute(
        select(func.count()).select_from(visible_exercises)
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
