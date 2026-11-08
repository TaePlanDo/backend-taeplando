"""Prepare eligible exercises for the future plan-generation algorithm."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.models.enums import EquipmentRequirementMode
from app.models.exercises import TrainerExercise
from app.models.training import TrainingGroup
from app.schemas.plan_generation import PlanGenerationParameters
from app.services.plan_generation_domain import PlanExerciseCandidate


async def prepare_candidates(
    session: AsyncSession,
    trainer_id: UUID,
    group: TrainingGroup,
    parameters: PlanGenerationParameters,
) -> tuple[PlanExerciseCandidate, ...]:
    """Build candidates compatible with the request and at least one group segment."""
    sources = await exercises_db.list_candidate_sources(
        session,
        trainer_id,
        min_age=group.min_age,
        max_age=group.max_age,
        participant_count=parameters.participant_count,
    )
    available_equipment_ids = set(parameters.available_equipment_ids)
    group_segment_ids = {item.segment_id for item in group.schema_items}
    candidates: list[PlanExerciseCandidate] = []
    for source in sources:
        candidate = _candidate_for_source(
            source, available_equipment_ids, group_segment_ids
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _candidate_for_source(
    source: TrainerExercise,
    available_equipment_ids: set[UUID],
    group_segment_ids: set[int],
) -> PlanExerciseCandidate | None:
    """Return one source only when its catalog requirements fit this request."""
    if not _has_required_equipment(source, available_equipment_ids):
        return None
    source_segment_ids = {segment.id for segment in source.segments}
    if not source_segment_ids & group_segment_ids:
        return None
    return PlanExerciseCandidate(
        trainer_exercise_id=source.id,
        exercise_id=source.exercise_id,
        exercise_version_id=source.source_version_id,
        min_age=source.min_age,
        max_age=source.max_age,
        min_participants=source.min_participants,
        max_participants=source.max_participants,
        default_duration_minutes=source.duration_minutes,
        equipment_requirement_mode=source.equipment_requirement_mode,
        equipment_ids=tuple(sorted(equipment.id for equipment in source.equipment)),
        training_type_ids=tuple(
            sorted(training_type.id for training_type in source.training_types)
        ),
        segment_ids=tuple(sorted(source_segment_ids)),
        physical_difficulty=source.physical_difficulty,
        technical_difficulty=source.technical_difficulty,
        upper_body_load=source.upper_body_load,
        lower_body_load=source.lower_body_load,
        core_load=source.core_load,
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
