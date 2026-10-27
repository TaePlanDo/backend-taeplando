"""Business operations for the exercise catalog."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.models.catalogs import Equipment, TrainingType
from app.models.enums import TrainerExerciseStatus
from app.models.exercises import Exercise, TrainerExercise
from app.schemas.common import PaginatedResponse, paginate
from app.schemas.exercise_list_filters import (
    EMPTY_EXERCISE_LIST_FILTERS,
    ExerciseListFilters,
)
from app.schemas.exercises import (
    CatalogReference,
    ExerciseConfigurationWrite,
    ExerciseResponse,
    ExerciseUpdate,
    ExerciseWrite,
    TrainingSegmentResponse,
)


class ExerciseNotFoundError(Exception):
    """Raised when a private exercise is absent or owned by another trainer."""


class InvalidExerciseConfigurationError(Exception):
    """Raised when a selected catalog value is unavailable to the trainer."""


async def list_exercises(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    page: int,
    page_size: int,
    filters: ExerciseListFilters = EMPTY_EXERCISE_LIST_FILTERS,
) -> PaginatedResponse[ExerciseResponse]:
    """Return one page of global and trainer-owned exercises."""
    db_page = await exercises_db.list_available_to_trainer(
        session,
        trainer_id,
        offset=(page - 1) * page_size,
        limit=page_size,
        filters=filters,
    )
    configurations = await exercises_db.list_configurations(
        session, trainer_id, db_page.items
    )
    return paginate(
        items=[
            _to_response(listed_exercise, configurations[listed_exercise.id])
            for listed_exercise in db_page.items
        ],
        total=db_page.total,
        page=page,
        page_size=page_size,
    )


async def create_exercise(
    session: AsyncSession, trainer_id: UUID, payload: ExerciseWrite
) -> ExerciseResponse:
    """Create an active private exercise owned by the authenticated trainer."""
    configuration = await _resolve_configuration_or_raise(session, trainer_id, payload)
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
    _replace_configuration(trainer_exercise, configuration)
    session.add_all((exercise, trainer_exercise))
    await session.commit()
    return _to_response_from_models(exercise, trainer_exercise, configuration)


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
    configuration = await _resolve_configuration_or_raise(session, trainer_id, payload)
    exercise.name = payload.name
    exercise.description = payload.description
    exercise.image_url = str(payload.image_url) if payload.image_url else None
    trainer_exercise.min_age = payload.min_age
    trainer_exercise.max_age = payload.max_age
    trainer_exercise.min_participants = payload.min_participants
    trainer_exercise.max_participants = payload.max_participants
    trainer_exercise.duration_minutes = payload.duration_minutes
    _replace_configuration(trainer_exercise, configuration)
    await session.commit()
    return _to_response_from_models(exercise, trainer_exercise, configuration)


async def delete_exercise(
    session: AsyncSession, trainer_id: UUID, exercise_id: UUID
) -> None:
    """Make a trainer-owned private exercise unavailable without deleting history."""
    _, trainer_exercise = await _get_owned_private_exercise_or_raise(
        session, trainer_id, exercise_id
    )
    trainer_exercise.status = TrainerExerciseStatus.INACTIVE
    await session.commit()


def _to_response(
    exercise: exercises_db.ListedExercise,
    configuration: exercises_db.ExerciseConfiguration,
) -> ExerciseResponse:
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
        equipment=_catalog_references(configuration.equipment),
        training_types=_catalog_references(configuration.training_types),
        segments=_segment_response(configuration),
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
    exercise: Exercise,
    trainer_exercise: TrainerExercise,
    configuration: exercises_db.ExerciseConfiguration,
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
        equipment=_catalog_references(configuration.equipment),
        training_types=_catalog_references(configuration.training_types),
        segments=_segment_response(configuration),
    )


async def _resolve_configuration_or_raise(
    session: AsyncSession,
    trainer_id: UUID,
    payload: ExerciseConfigurationWrite,
) -> exercises_db.ExerciseConfiguration:
    """Resolve visible catalog IDs supplied with a complete exercise payload."""
    configuration = await exercises_db.resolve_configuration(
        session,
        trainer_id,
        equipment_ids=payload.equipment_ids,
        training_type_ids=payload.training_type_ids,
        segment_ids=payload.segment_ids,
    )
    if configuration is None:
        raise InvalidExerciseConfigurationError
    return configuration


def _replace_configuration(
    trainer_exercise: TrainerExercise,
    configuration: exercises_db.ExerciseConfiguration,
) -> None:
    """Replace all mutable catalog relationships of one local configuration."""
    trainer_exercise.equipment = configuration.equipment
    trainer_exercise.training_types = configuration.training_types
    trainer_exercise.segments = configuration.segments


def _catalog_references(
    items: Sequence[Equipment | TrainingType],
) -> list[CatalogReference]:
    """Serialize equipment or training types with their common public shape."""
    return [CatalogReference(id=item.id, name=item.name) for item in items]


def _segment_response(
    configuration: exercises_db.ExerciseConfiguration,
) -> list[TrainingSegmentResponse]:
    """Serialize training segments from one exercise configuration."""
    return [
        TrainingSegmentResponse(id=item.id, code=item.code, name=item.name)
        for item in configuration.segments
    ]
