"""Database queries for global and trainer-owned exercises."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    SQLColumnExpression,
    exists,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from app.db import catalogs as catalogs_db
from app.db.sql_filters import ilike_contains
from app.models.associations import (
    exercise_version_equipment,
    exercise_version_segments,
    exercise_version_training_types,
    trainer_exercise_equipment,
    trainer_exercise_segments,
    trainer_exercise_training_types,
)
from app.models.catalogs import Equipment, TrainingSegment, TrainingType
from app.models.enums import (
    EquipmentRequirementMode,
    ExerciseScope,
    ExerciseVersionStatus,
    TrainerExerciseStatus,
)
from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise
from app.schemas.exercise_list_filters import (
    EMPTY_EXERCISE_LIST_FILTERS,
    ExerciseListFilters,
)


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
    equipment_requirement_mode: EquipmentRequirementMode
    physical_difficulty: int
    technical_difficulty: int
    upper_body_load: int
    lower_body_load: int
    core_load: int
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


class _BranchColumns(NamedTuple):
    """Column/association map for one side of the private ∪ global union."""

    name: SQLColumnExpression[str]
    min_age: SQLColumnExpression[int]
    max_age: SQLColumnExpression[int]
    min_participants: SQLColumnExpression[int]
    max_participants: SQLColumnExpression[int]
    physical_difficulty: SQLColumnExpression[int]
    technical_difficulty: SQLColumnExpression[int]
    upper_body_load: SQLColumnExpression[int]
    lower_body_load: SQLColumnExpression[int]
    core_load: SQLColumnExpression[int]
    status: SQLColumnExpression[TrainerExerciseStatus]
    owner_id: SQLColumnExpression[UUID]
    equipment_owner_fk: SQLColumnExpression[UUID]
    equipment_value: SQLColumnExpression[UUID]
    training_types_owner_fk: SQLColumnExpression[UUID]
    training_types_value: SQLColumnExpression[UUID]
    segments_owner_fk: SQLColumnExpression[UUID]
    segments_value: SQLColumnExpression[int]


_PRIVATE_BRANCH = _BranchColumns(
    name=Exercise.name,
    min_age=TrainerExercise.min_age,
    max_age=TrainerExercise.max_age,
    min_participants=TrainerExercise.min_participants,
    max_participants=TrainerExercise.max_participants,
    physical_difficulty=TrainerExercise.physical_difficulty,
    technical_difficulty=TrainerExercise.technical_difficulty,
    upper_body_load=TrainerExercise.upper_body_load,
    lower_body_load=TrainerExercise.lower_body_load,
    core_load=TrainerExercise.core_load,
    status=TrainerExercise.status,
    owner_id=TrainerExercise.id,
    equipment_owner_fk=trainer_exercise_equipment.c.trainer_exercise_id,
    equipment_value=trainer_exercise_equipment.c.equipment_id,
    training_types_owner_fk=trainer_exercise_training_types.c.trainer_exercise_id,
    training_types_value=trainer_exercise_training_types.c.training_type_id,
    segments_owner_fk=trainer_exercise_segments.c.trainer_exercise_id,
    segments_value=trainer_exercise_segments.c.segment_id,
)

_GLOBAL_BRANCH = _BranchColumns(
    name=ExerciseVersion.name,
    min_age=ExerciseVersion.min_age,
    max_age=ExerciseVersion.max_age,
    min_participants=ExerciseVersion.min_participants,
    max_participants=ExerciseVersion.max_participants,
    physical_difficulty=ExerciseVersion.physical_difficulty,
    technical_difficulty=ExerciseVersion.technical_difficulty,
    upper_body_load=ExerciseVersion.upper_body_load,
    lower_body_load=ExerciseVersion.lower_body_load,
    core_load=ExerciseVersion.core_load,
    status=func.coalesce(
        TrainerExercise.status,
        literal(
            TrainerExerciseStatus.ACTIVE,
            type_=TrainerExercise.__table__.c.status.type,
        ),
    ),
    owner_id=ExerciseVersion.id,
    equipment_owner_fk=exercise_version_equipment.c.exercise_version_id,
    equipment_value=exercise_version_equipment.c.equipment_id,
    training_types_owner_fk=exercise_version_training_types.c.exercise_version_id,
    training_types_value=exercise_version_training_types.c.training_type_id,
    segments_owner_fk=exercise_version_segments.c.exercise_version_id,
    segments_value=exercise_version_segments.c.segment_id,
)


async def list_available_to_trainer(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    offset: int,
    limit: int,
    filters: ExerciseListFilters = EMPTY_EXERCISE_LIST_FILTERS,
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
            _PRIVATE_BRANCH.status,
            TrainerExercise.equipment_requirement_mode,
            TrainerExercise.physical_difficulty,
            TrainerExercise.technical_difficulty,
            TrainerExercise.upper_body_load,
            TrainerExercise.lower_body_load,
            TrainerExercise.core_load,
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
            TrainerExercise.status.in_(
                (TrainerExerciseStatus.ACTIVE, TrainerExerciseStatus.SUSPENDED)
            ),
            *_filters_for_branch(_PRIVATE_BRANCH, filters),
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
            _GLOBAL_BRANCH.status.label("status"),
            ExerciseVersion.equipment_requirement_mode,
            ExerciseVersion.physical_difficulty,
            ExerciseVersion.technical_difficulty,
            ExerciseVersion.upper_body_load,
            ExerciseVersion.lower_body_load,
            ExerciseVersion.core_load,
            Exercise.latest_approved_version_id.label("version_id"),
        )
        .join(
            ExerciseVersion, ExerciseVersion.id == Exercise.latest_approved_version_id
        )
        .outerjoin(
            TrainerExercise,
            (TrainerExercise.exercise_id == Exercise.id)
            & (TrainerExercise.trainer_id == trainer_id),
        )
        .where(
            Exercise.scope == ExerciseScope.GLOBAL,
            ExerciseVersion.status == ExerciseVersionStatus.APPROVED,
            *_filters_for_branch(_GLOBAL_BRANCH, filters),
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


async def list_candidate_sources(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    min_age: int,
    max_age: int,
    participant_count: int,
) -> list[TrainerExercise]:
    """Return active trainer configurations that match group and size ranges."""
    result = await session.scalars(
        select(TrainerExercise)
        .join(Exercise)
        .options(*_configuration_loader_options(TrainerExercise))
        .where(
            TrainerExercise.trainer_id == trainer_id,
            TrainerExercise.status == TrainerExerciseStatus.ACTIVE,
            TrainerExercise.max_age >= min_age,
            TrainerExercise.min_age <= max_age,
            TrainerExercise.min_participants <= participant_count,
            TrainerExercise.max_participants >= participant_count,
            or_(
                Exercise.scope == ExerciseScope.GLOBAL,
                Exercise.owner_user_id == trainer_id,
            ),
        )
        .order_by(TrainerExercise.id)
    )
    return list(result.unique())


async def list_sources_for_generated_plan(
    session: AsyncSession, trainer_id: UUID, source_ids: set[UUID]
) -> dict[UUID, TrainerExercise]:
    """Load selected trainer configurations and immutable snapshot relations."""
    if not source_ids:
        return {}
    result = await session.scalars(
        select(TrainerExercise)
        .where(
            TrainerExercise.trainer_id == trainer_id,
            TrainerExercise.id.in_(source_ids),
        )
        .options(
            *_configuration_loader_options(TrainerExercise),
            selectinload(TrainerExercise.exercise),
            selectinload(TrainerExercise.source_version),
        )
    )
    return {source.id: source for source in result.unique()}


def _filters_for_branch(
    columns: _BranchColumns, filters: ExerciseListFilters
) -> list[ColumnElement[bool]]:
    """Build scalar + catalog predicates for one union branch."""
    predicates: list[ColumnElement[bool]] = []
    if filters.name is not None:
        predicates.append(ilike_contains(columns.name, filters.name))
    if filters.status is not None:
        predicates.append(columns.status == filters.status)
    for minimum, maximum, lower_column, upper_column in (
        (filters.min_age, filters.max_age, columns.min_age, columns.max_age),
        (
            filters.min_participants,
            filters.max_participants,
            columns.min_participants,
            columns.max_participants,
        ),
        (
            filters.min_physical_difficulty,
            filters.max_physical_difficulty,
            columns.physical_difficulty,
            columns.physical_difficulty,
        ),
        (
            filters.min_technical_difficulty,
            filters.max_technical_difficulty,
            columns.technical_difficulty,
            columns.technical_difficulty,
        ),
        (
            filters.min_upper_body_load,
            filters.max_upper_body_load,
            columns.upper_body_load,
            columns.upper_body_load,
        ),
        (
            filters.min_lower_body_load,
            filters.max_lower_body_load,
            columns.lower_body_load,
            columns.lower_body_load,
        ),
        (
            filters.min_core_load,
            filters.max_core_load,
            columns.core_load,
            columns.core_load,
        ),
    ):
        if minimum is not None:
            predicates.append(upper_column >= minimum)
        if maximum is not None:
            predicates.append(lower_column <= maximum)

    for ids, owner_fk, value_column in (
        (filters.equipment_ids, columns.equipment_owner_fk, columns.equipment_value),
        (
            filters.training_type_ids,
            columns.training_types_owner_fk,
            columns.training_types_value,
        ),
        (filters.segment_ids, columns.segments_owner_fk, columns.segments_value),
    ):
        if ids:
            predicates.append(
                exists(
                    select(literal(1)).where(
                        owner_fk == columns.owner_id,
                        value_column.in_(ids),
                    )
                )
            )
    return predicates


async def resolve_configuration(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    equipment_ids: list[UUID],
    training_type_ids: list[UUID],
    segment_ids: list[int],
) -> ExerciseConfiguration | None:
    """Return catalog values visible to the trainer or reject an unavailable ID."""
    equipment = await catalogs_db.list_visible_by_ids(
        session,
        trainer_id,
        catalog=Equipment,
        ids=equipment_ids,
    )
    training_types = await catalogs_db.list_visible_by_ids(
        session,
        trainer_id,
        catalog=TrainingType,
        ids=training_type_ids,
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
        exercise.version_id for exercise in exercises if exercise.version_id is not None
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
    equipment_requirement_mode: EquipmentRequirementMode,
    physical_difficulty: int,
    technical_difficulty: int,
    upper_body_load: int,
    lower_body_load: int,
    core_load: int,
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
        equipment_requirement_mode=equipment_requirement_mode,
        physical_difficulty=physical_difficulty,
        technical_difficulty=technical_difficulty,
        upper_body_load=upper_body_load,
        lower_body_load=lower_body_load,
        core_load=core_load,
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


async def get_configuration_for_trainer(
    session: AsyncSession, trainer_id: UUID, exercise_id: UUID
) -> TrainerExercise | None:
    """Find the trainer-local configuration for one exercise."""
    return await session.scalar(
        select(TrainerExercise).where(
            TrainerExercise.trainer_id == trainer_id,
            TrainerExercise.exercise_id == exercise_id,
        )
    )


async def create_configuration_for_global_exercise(
    session: AsyncSession, trainer_id: UUID, exercise_id: UUID
) -> TrainerExercise | None:
    """Copy the current approved global version into one trainer configuration."""
    source_version = await session.scalar(
        select(ExerciseVersion)
        .join(Exercise, Exercise.id == ExerciseVersion.exercise_id)
        .where(
            Exercise.id == exercise_id,
            Exercise.scope == ExerciseScope.GLOBAL,
            Exercise.latest_approved_version_id == ExerciseVersion.id,
            ExerciseVersion.status == ExerciseVersionStatus.APPROVED,
        )
        .options(*_configuration_loader_options(ExerciseVersion))
    )
    if source_version is None:
        return None

    trainer_exercise = TrainerExercise(
        trainer_id=trainer_id,
        exercise_id=source_version.exercise_id,
        source_version_id=source_version.id,
        status=TrainerExerciseStatus.ACTIVE,
        min_age=source_version.min_age,
        max_age=source_version.max_age,
        min_participants=source_version.min_participants,
        max_participants=source_version.max_participants,
        duration_minutes=source_version.duration_minutes,
        equipment_requirement_mode=source_version.equipment_requirement_mode,
        physical_difficulty=source_version.physical_difficulty,
        technical_difficulty=source_version.technical_difficulty,
        upper_body_load=source_version.upper_body_load,
        lower_body_load=source_version.lower_body_load,
        core_load=source_version.core_load,
    )
    trainer_exercise.equipment = list(source_version.equipment)
    trainer_exercise.training_types = list(source_version.training_types)
    trainer_exercise.segments = list(source_version.segments)
    session.add(trainer_exercise)
    return trainer_exercise
