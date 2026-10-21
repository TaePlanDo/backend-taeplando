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
    image_url: str | None
    min_age: int
    max_age: int
    min_participants: int
    max_participants: int
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
            Exercise.image_url,
            TrainerExercise.min_age,
            TrainerExercise.max_age,
            TrainerExercise.min_participants,
            TrainerExercise.max_participants,
            TrainerExercise.duration_minutes,
            TrainerExercise.status,
        )
        .join(TrainerExercise)
        .where(
            Exercise.scope == ExerciseScope.PRIVATE,
            Exercise.owner_user_id == trainer_id,
            TrainerExercise.trainer_id == trainer_id,
            TrainerExercise.status == TrainerExerciseStatus.ACTIVE,
        )
    )
    global_exercises = (
        select(
            Exercise.id,
            Exercise.owner_user_id,
            Exercise.scope,
            ExerciseVersion.name,
            ExerciseVersion.description,
            ExerciseVersion.image_url,
            ExerciseVersion.min_age,
            ExerciseVersion.max_age,
            ExerciseVersion.min_participants,
            ExerciseVersion.max_participants,
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
            items=[ListedExercise(*row[:12]) for row in rows], total=rows[0][12]
        )
    if offset == 0:
        return ExercisePage(items=[], total=0)

    total_result = await session.execute(
        select(func.count()).select_from(visible_exercises)
    )
    return ExercisePage(items=[], total=total_result.scalar_one())


def create_for_trainer(
    trainer_id: UUID,
    *,
    name: str,
    description: str,
    image_url: str | None,
    min_age: int,
    max_age: int,
    min_participants: int,
    max_participants: int,
    duration_minutes: int,
) -> tuple[Exercise, TrainerExercise]:
    """Build a private exercise and its active trainer configuration."""
    exercise = Exercise(
        owner_user_id=trainer_id,
        scope=ExerciseScope.PRIVATE,
        name=name,
        description=description,
        image_url=image_url,
    )
    trainer_exercise = TrainerExercise(
        trainer_id=trainer_id,
        exercise=exercise,
        status=TrainerExerciseStatus.ACTIVE,
        min_age=min_age,
        max_age=max_age,
        min_participants=min_participants,
        max_participants=max_participants,
        duration_minutes=duration_minutes,
    )
    return exercise, trainer_exercise


async def get_private_for_trainer(
    session: AsyncSession, trainer_id: UUID, exercise_id: UUID
) -> tuple[Exercise, TrainerExercise] | None:
    """Find one private exercise together with its owner's configuration."""
    result = await session.execute(
        select(Exercise, TrainerExercise)
        .join(TrainerExercise)
        .where(
            Exercise.id == exercise_id,
            Exercise.scope == ExerciseScope.PRIVATE,
            Exercise.owner_user_id == trainer_id,
            TrainerExercise.trainer_id == trainer_id,
        )
    )
    return result.one_or_none()
