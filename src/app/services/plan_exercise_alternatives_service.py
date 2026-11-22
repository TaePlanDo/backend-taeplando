"""Rank alternative exercises for one saved plan slot."""

from collections.abc import Sequence
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.db import training_plans as training_plans_db
from app.models.catalogs import Equipment, TrainingType
from app.models.exercises import TrainerExercise
from app.models.training import TrainingPlan, TrainingPlanExercise
from app.schemas.exercises import CatalogReference, TrainingSegmentResponse
from app.schemas.training_plans import (
    PlanExerciseAlternative,
    PlanSchemaSnapshotItem,
)
from app.services.plan_exercise_similarity import (
    SimilarityLabels,
    label_similarity,
    labels_from_candidate,
)
from app.services.plan_generation_candidates_service import try_build_candidate
from app.services.plan_generation_domain import PlanExerciseCandidate
from app.services.training_plan_service import PlanNotFoundError

_CATALOG_SNAPSHOTS = TypeAdapter(list[CatalogReference])
_SCHEMA_SNAPSHOTS = TypeAdapter(list[PlanSchemaSnapshotItem])
_SEGMENT_SNAPSHOTS = TypeAdapter(list[TrainingSegmentResponse])


class PlanExerciseNotFoundError(Exception):
    """Raised when a plan slot is absent on an owned plan."""


async def list_alternatives(
    session: AsyncSession,
    trainer_id: UUID,
    plan_id: UUID,
    plan_exercise_id: UUID,
    *,
    limit: int = 20,
) -> list[PlanExerciseAlternative]:
    """Return hard-filtered alternatives ranked by label similarity."""
    plan = await training_plans_db.get_for_trainer(session, trainer_id, plan_id)
    if plan is None:
        raise PlanNotFoundError
    slot = _slot_or_raise(plan, plan_exercise_id)
    segment_id = _segment_id_for_slot(plan, slot)
    available_equipment_ids = _catalog_ids(plan.available_equipment_snapshot)
    excluded_exercise_ids = {exercise.exercise_id for exercise in plan.exercises}

    await exercises_db.ensure_global_configurations_for_trainer(session, trainer_id)
    sources = await exercises_db.list_candidate_sources(
        session,
        trainer_id,
        min_age=plan.group_min_age_snapshot,
        max_age=plan.group_max_age_snapshot,
        participant_count=plan.participant_count,
    )
    reference = _labels_from_slot(slot)
    ranked: list[tuple[float, PlanExerciseCandidate]] = []
    for source in sources:
        if source.exercise_id in excluded_exercise_ids:
            continue
        candidate = try_build_candidate(
            source,
            available_equipment_ids,
            {segment_id},
        )
        if candidate is None:
            continue
        score = label_similarity(reference, labels_from_candidate(candidate))
        ranked.append((score, candidate))

    ranked.sort(key=lambda item: (-item[0], item[1].exercise_id))
    limited = ranked[:limit]
    if not limited:
        return []

    named_sources = await exercises_db.list_sources_for_generated_plan(
        session,
        trainer_id,
        {candidate.trainer_exercise_id for _score, candidate in limited},
    )
    return [
        _to_alternative(score, candidate, named_sources) for score, candidate in limited
    ]


def _to_alternative(
    score: float,
    candidate: PlanExerciseCandidate,
    named_sources: dict[UUID, TrainerExercise],
) -> PlanExerciseAlternative:
    source = named_sources[candidate.trainer_exercise_id]
    details = source.source_version or source.exercise
    return PlanExerciseAlternative(
        trainer_exercise_id=candidate.trainer_exercise_id,
        exercise_id=candidate.exercise_id,
        name=details.name,
        image_url=details.image_url,
        physical_difficulty=candidate.physical_difficulty,
        technical_difficulty=candidate.technical_difficulty,
        upper_body_load=candidate.upper_body_load,
        lower_body_load=candidate.lower_body_load,
        core_load=candidate.core_load,
        equipment=_catalog_refs(source.equipment),
        training_types=_catalog_refs(source.training_types),
        similarity_score=score,
    )


def _catalog_refs(
    items: Sequence[Equipment | TrainingType],
) -> list[CatalogReference]:
    return [
        CatalogReference(id=item.id, name=item.name)
        for item in sorted(items, key=lambda entry: (entry.name, entry.id))
    ]


def _slot_or_raise(plan: TrainingPlan, plan_exercise_id: UUID) -> TrainingPlanExercise:
    for exercise in plan.exercises:
        if exercise.id == plan_exercise_id:
            return exercise
    raise PlanExerciseNotFoundError


def _segment_id_for_slot(plan: TrainingPlan, slot: TrainingPlanExercise) -> int:
    for item in _SCHEMA_SNAPSHOTS.validate_python(plan.schema_snapshot):
        if item.position == slot.schema_position:
            return item.segment_id
    raise PlanExerciseNotFoundError


def _catalog_ids(items: list[dict[str, object]]) -> set[UUID]:
    return {item.id for item in _CATALOG_SNAPSHOTS.validate_python(items)}


def _segment_ids(items: list[dict[str, object]]) -> frozenset[int]:
    return frozenset(item.id for item in _SEGMENT_SNAPSHOTS.validate_python(items))


def _labels_from_slot(slot: TrainingPlanExercise) -> SimilarityLabels:
    return SimilarityLabels(
        equipment_ids=frozenset(_catalog_ids(slot.equipment_snapshot)),
        training_type_ids=frozenset(_catalog_ids(slot.training_types_snapshot)),
        segment_ids=_segment_ids(slot.segments_snapshot),
        physical_difficulty=slot.physical_difficulty_snapshot,
        technical_difficulty=slot.technical_difficulty_snapshot,
        upper_body_load=slot.upper_body_load_snapshot,
        lower_body_load=slot.lower_body_load_snapshot,
        core_load=slot.core_load_snapshot,
    )
