"""Prepare eligible exercises for the future plan-generation algorithm."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.models.enums import EquipmentRequirementMode
from app.models.exercises import TrainerExercise
from app.models.training import TrainingGroup
from app.schemas.plan_generation import PlanGenerationParameters


@dataclass(frozen=True)
class PlanExerciseCandidate:
    """One exercise configuration eligible for one or more group-schema items."""

    trainer_exercise_id: UUID
    exercise_id: UUID
    exercise_version_id: UUID | None
    duration_minutes: int
    schema_positions: tuple[int, ...]


async def prepare_candidates(
    session: AsyncSession,
    trainer_id: UUID,
    group: TrainingGroup,
    parameters: PlanGenerationParameters,
) -> list[PlanExerciseCandidate]:
    """Build disposable candidates after request validation and before generation."""
    sources = await exercises_db.list_candidate_sources(
        session,
        trainer_id,
        min_age=group.min_age,
        max_age=group.max_age,
        participant_count=parameters.participant_count,
    )
    available_equipment_ids = set(parameters.available_equipment_ids)
    candidates: list[PlanExerciseCandidate] = []
    for source in sources:
        candidate = _candidate_for_source(
            source,
            group,
            available_equipment_ids,
            parameters.training_type_id,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate_for_source(
    source: TrainerExercise,
    group: TrainingGroup,
    available_equipment_ids: set[UUID],
    training_type_id: UUID | None,
) -> PlanExerciseCandidate | None:
    """Return one source only when its catalog requirements fit this request."""
    if not _has_required_equipment(source, available_equipment_ids):
        return None
    if not _has_training_type(source, training_type_id):
        return None

    source_segment_ids = {segment.id for segment in source.segments}
    schema_positions = tuple(
        item.position
        for item in group.schema_items
        if item.segment_id in source_segment_ids
    )
    if not schema_positions:
        return None
    return PlanExerciseCandidate(
        trainer_exercise_id=source.id,
        exercise_id=source.exercise_id,
        exercise_version_id=source.source_version_id,
        duration_minutes=source.duration_minutes,
        schema_positions=schema_positions,
    )


def _has_required_equipment(
    source: TrainerExercise, available_equipment_ids: set[UUID]
) -> bool:
    """Apply the configuration's ALL or ANY equipment requirement."""
    required_equipment_ids = {equipment.id for equipment in source.equipment}
    if source.equipment_requirement_mode == EquipmentRequirementMode.ALL:
        return required_equipment_ids <= available_equipment_ids
    return not required_equipment_ids or bool(
        required_equipment_ids & available_equipment_ids
    )


def _has_training_type(source: TrainerExercise, training_type_id: UUID | None) -> bool:
    """Accept every type for automatic selection, otherwise require the chosen type."""
    return training_type_id is None or any(
        training_type.id == training_type_id for training_type in source.training_types
    )
