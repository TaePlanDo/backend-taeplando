"""Prepare eligible exercises for the future plan-generation algorithm."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.models.enums import EquipmentRequirementMode
from app.models.exercises import TrainerExercise
from app.models.training import TrainingGroup, TrainingGroupSchemaItem
from app.schemas.plan_generation import PlanGenerationParameters
from app.services.plan_generation_domain import (
    GenerationSchemaItem,
    PlanExerciseCandidate,
)
from app.services.plan_generation_errors import NoCandidateForSchemaPositionError


async def prepare_candidates(
    session: AsyncSession,
    trainer_id: UUID,
    group: TrainingGroup,
    parameters: PlanGenerationParameters,
) -> Mapping[int, tuple[PlanExerciseCandidate, ...]]:
    """Build one hard-filtered candidate pool for every group-schema segment."""
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
        candidate = _candidate_for_source(source, available_equipment_ids)
        if candidate is not None:
            candidates.append(candidate)
    return build_candidates_by_position(group.schema_items, candidates)


def build_candidates_by_position(
    schema: Sequence[GenerationSchemaItem | TrainingGroupSchemaItem],
    candidates: Sequence[PlanExerciseCandidate],
) -> Mapping[int, tuple[PlanExerciseCandidate, ...]]:
    """Index structurally valid candidates once for all generation phases."""
    candidates_by_position: dict[int, list[PlanExerciseCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.default_duration_minutes < 1:
            continue
        for schema_item in schema:
            if schema_item.segment_id in candidate.segment_ids:
                candidates_by_position[schema_item.position].append(candidate)

    for schema_item in schema:
        if not candidates_by_position[schema_item.position]:
            raise NoCandidateForSchemaPositionError(schema_item.position)
    return MappingProxyType(
        {
            schema_item.position: tuple(candidates_by_position[schema_item.position])
            for schema_item in schema
        }
    )


def _candidate_for_source(
    source: TrainerExercise,
    available_equipment_ids: set[UUID],
) -> PlanExerciseCandidate | None:
    """Return one source only when its catalog requirements fit this request."""
    if not _has_required_equipment(source, available_equipment_ids):
        return None
    source_segment_ids = {segment.id for segment in source.segments}
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
