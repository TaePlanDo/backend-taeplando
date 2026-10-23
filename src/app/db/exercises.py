"""Database queries for global and trainer-owned exercises."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from app.models.catalogs import Equipment, TrainingSegment, TrainingType
from app.models.enums import (
    CatalogVisibility,
    ExerciseScope,
    ExerciseVersionStatus,
    TrainerExerciseStatus,
)
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
    version_id: UUID | None


class ExerciseConfiguration(NamedTuple):
    """Resolved catalog values assigned to one exercise configuration."""

    equipment: list[Equipment]
    training_types: list[TrainingType]
    segments: list[TrainingSegment]


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
            literal(
                None,
                type_=Exercise.__table__.c.latest_approved_version_id.type,
            ).label("version_id"),
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
            Exercise.latest_approved_version_id.label("version_id"),
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
            items=[ListedExercise(*row[:-1]) for row in rows], total=rows[0][-1]
        )
    if offset == 0:
        return ExercisePage(items=[], total=0)

    total_result = await session.execute(
        select(func.count()).select_from(visible_exercises)
    )
    return ExercisePage(items=[], total=total_result.scalar_one())


async def resolve_configuration(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    equipment_ids: list[UUID],
    training_type_ids: list[UUID],
    segment_ids: list[int],
) -> ExerciseConfiguration | None:
    """Return catalog values visible to the trainer or reject an unavailable ID."""
    equipment = await _visible_equipment(session, trainer_id, equipment_ids)
    training_types = await _visible_training_types(
        session, trainer_id, training_type_ids
    )
    segments = await _segments_by_id(session, segment_ids)
    if (
        len(equipment) != len(equipment_ids)
        or len(training_types) != len(training_type_ids)
        or len(segments) != len(segment_ids)
    ):
        return None
    return _configuration(equipment, training_types, segments)


async def list_configurations(
    session: AsyncSession, trainer_id: UUID, exercises: list[ListedExercise]
) -> dict[UUID, ExerciseConfiguration]:
    """Load configuration for a mixed page of private and global exercises."""
    private_exercise_ids = [
        exercise.id for exercise in exercises if exercise.scope == ExerciseScope.PRIVATE
    ]
    global_version_ids = [
        exercise.version_id
        for exercise in exercises
        if exercise.version_id is not None
    ]
    configurations: dict[UUID, ExerciseConfiguration] = {}
    if private_exercise_ids:
        private_result = await session.scalars(
            select(TrainerExercise)
            .where(
                TrainerExercise.exercise_id.in_(private_exercise_ids),
                TrainerExercise.trainer_id == trainer_id,
            )
            .options(*_configuration_loader_options(TrainerExercise))
        )
        for trainer_exercise in private_result:
            configurations[trainer_exercise.exercise_id] = _configuration_from(
                trainer_exercise
            )
    if global_version_ids:
        global_result = await session.scalars(
            select(ExerciseVersion)
            .where(ExerciseVersion.id.in_(global_version_ids))
            .options(*_configuration_loader_options(ExerciseVersion))
        )
        versions = {version.id: version for version in global_result}
        for exercise in exercises:
            if exercise.version_id is not None:
                configurations[exercise.id] = _configuration_from(
                    versions[exercise.version_id]
                )
    return configurations


async def _visible_equipment(
    session: AsyncSession, trainer_id: UUID, equipment_ids: list[UUID]
) -> list[Equipment]:
    """Load equipment that is global or belongs to the authenticated trainer."""
    if not equipment_ids:
        return []
    result = await session.scalars(
        select(Equipment).where(
            Equipment.id.in_(equipment_ids),
            or_(
                Equipment.visibility == CatalogVisibility.GLOBAL,
                Equipment.owner_user_id == trainer_id,
            ),
        )
    )
    return list(result)


async def _visible_training_types(
    session: AsyncSession, trainer_id: UUID, training_type_ids: list[UUID]
) -> list[TrainingType]:
    """Load training types that are global or belong to the authenticated trainer."""
    result = await session.scalars(
        select(TrainingType).where(
            TrainingType.id.in_(training_type_ids),
            or_(
                TrainingType.visibility == CatalogVisibility.GLOBAL,
                TrainingType.owner_user_id == trainer_id,
            ),
        )
    )
    return list(result)


async def _segments_by_id(
    session: AsyncSession, segment_ids: list[int]
) -> list[TrainingSegment]:
    """Load entries from the fixed training-segment dictionary."""
    result = await session.scalars(
        select(TrainingSegment).where(TrainingSegment.id.in_(segment_ids))
    )
    return list(result)


def _configuration_loader_options(
    model: type[TrainerExercise] | type[ExerciseVersion],
) -> tuple[LoaderOption, ...]:
    """Return eager loaders shared by private and published configurations."""
    return (
        selectinload(model.equipment),
        selectinload(model.training_types),
        selectinload(model.segments),
    )


def _configuration_from(
    source: TrainerExercise | ExerciseVersion,
) -> ExerciseConfiguration:
    """Map ORM relationships to the shared configuration value object."""
    return _configuration(source.equipment, source.training_types, source.segments)


def _configuration(
    equipment: list[Equipment],
    training_types: list[TrainingType],
    segments: list[TrainingSegment],
) -> ExerciseConfiguration:
    """Normalize catalog ordering in every public exercise configuration."""
    return ExerciseConfiguration(
        equipment=sorted(equipment, key=lambda item: (item.name, item.id)),
        training_types=sorted(training_types, key=lambda item: (item.name, item.id)),
        segments=sorted(segments, key=lambda item: item.id),
    )


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
        .options(*_configuration_loader_options(TrainerExercise))
    )
    return result.tuples().one_or_none()
