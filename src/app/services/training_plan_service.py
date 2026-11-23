"""Business operations for a trainer's saved training plans."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import exercises as exercises_db
from app.db import training_plans as training_plans_db
from app.models.enums import TrainerExerciseStatus
from app.models.exercises import TrainerExercise
from app.models.training import TrainingPlan, TrainingPlanExercise
from app.schemas.common import PaginatedResponse, paginate
from app.schemas.exercises import CatalogReference, TrainingSegmentResponse
from app.schemas.training_plans import (
    PlanDetail,
    PlanExerciseResponse,
    PlanListItem,
    PlanSchemaSnapshotItem,
    TrainingPlanListFilters,
)
from app.services.plan_exercise_snapshots import fill_plan_exercise_from_source

_CATALOG_SNAPSHOTS = TypeAdapter(list[CatalogReference])
_SCHEMA_SNAPSHOTS = TypeAdapter(list[PlanSchemaSnapshotItem])
_SEGMENT_SNAPSHOTS = TypeAdapter(list[TrainingSegmentResponse])


class PlanResourceNotFoundError(Exception):
    """Uniform not-found boundary for plan mutation HTTP mapping."""

    detail = "Plan not found"


class PlanNotFoundError(PlanResourceNotFoundError):
    """Raised when a plan is absent or belongs to another trainer."""


class PlanExerciseNotFoundError(PlanResourceNotFoundError):
    """Raised when a plan slot is absent on an owned plan."""

    detail = "Plan exercise not found"


class PlanExerciseUnavailableError(PlanResourceNotFoundError):
    """Raised when the replacement exercise is not available to the trainer."""

    detail = "Exercise not found"


class PlanStructureInvalidError(Exception):
    """Raised when a plan structure update is not an exact slot permutation."""

    detail = "Plan exercise order must list each current plan exercise once"


async def list_plans(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    filters: TrainingPlanListFilters,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[PlanListItem]:
    """List one newest-first page of plans owned by one trainer."""
    db_page = await training_plans_db.list_for_trainer(
        session,
        trainer_id,
        filters=filters,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return paginate(
        items=[_to_list_item(plan) for plan in db_page.items],
        total=db_page.total,
        page=page,
        page_size=page_size,
    )


async def get_plan(
    session: AsyncSession, trainer_id: UUID, plan_id: UUID
) -> PlanDetail:
    """Return a single owned plan with ordered exercise snapshots."""
    return _to_detail(await _get_owned_or_raise(session, trainer_id, plan_id))


async def delete_plan(session: AsyncSession, trainer_id: UUID, plan_id: UUID) -> None:
    """Delete an owned plan together with its dependent exercise snapshots."""
    plan = await _get_owned_or_raise(session, trainer_id, plan_id)
    await session.delete(plan)
    await session.commit()


async def replace_plan_exercise(
    session: AsyncSession,
    trainer_id: UUID,
    plan_id: UUID,
    plan_exercise_id: UUID,
    exercise_id: UUID,
) -> PlanExerciseResponse:
    """Replace one plan slot's identity and snapshots, keeping order and duration."""
    plan = await _get_owned_or_raise(session, trainer_id, plan_id, for_update=True)
    slot = _slot_or_raise(plan, plan_exercise_id)
    source = await _resolve_active_source(session, trainer_id, exercise_id)
    fill_plan_exercise_from_source(
        slot,
        source,
        duration_minutes=slot.duration_minutes_snapshot,
    )
    await session.commit()
    return _to_exercise(slot)


async def delete_plan_exercise(
    session: AsyncSession,
    trainer_id: UUID,
    plan_id: UUID,
    plan_exercise_id: UUID,
) -> None:
    """Remove one plan slot and renumber remaining positions to 1..n."""
    plan = await _get_owned_or_raise(session, trainer_id, plan_id, for_update=True)
    plan.exercises.remove(_slot_or_raise(plan, plan_exercise_id))
    await session.flush()
    remaining = sorted(plan.exercises, key=lambda item: item.position)
    await _rewrite_positions(session, remaining)
    await session.commit()


async def update_plan_structure(
    session: AsyncSession,
    trainer_id: UUID,
    plan_id: UUID,
    *,
    name: str,
    plan_exercise_ids: Sequence[UUID],
) -> PlanDetail:
    """Rename a plan and rewrite exercise display order in one locked update."""
    plan = await _get_owned_or_raise(session, trainer_id, plan_id, for_update=True)
    by_id = {exercise.id: exercise for exercise in plan.exercises}
    if len(plan_exercise_ids) != len(by_id) or set(plan_exercise_ids) != set(by_id):
        raise PlanStructureInvalidError
    plan.name = name
    await _rewrite_positions(
        session, [by_id[exercise_id] for exercise_id in plan_exercise_ids]
    )
    await session.commit()
    return _to_detail(plan)


async def _rewrite_positions(
    session: AsyncSession, ordered_exercises: Sequence[TrainingPlanExercise]
) -> None:
    """Park then assign 1..n so unique (plan_id, position) never collides mid-update."""
    if not ordered_exercises:
        return
    temporary_base = max(exercise.position for exercise in ordered_exercises)
    for offset, exercise in enumerate(ordered_exercises, start=1):
        exercise.position = temporary_base + offset
    await session.flush()
    for position, exercise in enumerate(ordered_exercises, start=1):
        exercise.position = position


async def _get_owned_or_raise(
    session: AsyncSession,
    trainer_id: UUID,
    plan_id: UUID,
    *,
    for_update: bool = False,
) -> TrainingPlan:
    """Return an owned plan or raise a uniform not-found outcome."""
    plan = await training_plans_db.get_for_trainer(
        session, trainer_id, plan_id, for_update=for_update
    )
    if plan is None:
        raise PlanNotFoundError
    return plan


def _slot_or_raise(plan: TrainingPlan, plan_exercise_id: UUID) -> TrainingPlanExercise:
    """Return one exercise slot on the plan or raise a uniform not-found outcome."""
    for exercise in plan.exercises:
        if exercise.id == plan_exercise_id:
            return exercise
    raise PlanExerciseNotFoundError


async def _resolve_active_source(
    session: AsyncSession, trainer_id: UUID, exercise_id: UUID
) -> TrainerExercise:
    """Resolve one active trainer configuration for a single replacement exercise."""
    configuration = await exercises_db.get_plan_source_for_trainer(
        session, trainer_id, exercise_id
    )
    if configuration is None:
        configuration = await exercises_db.create_configuration_for_global_exercise(
            session, trainer_id, exercise_id
        )
        if configuration is None:
            raise PlanExerciseUnavailableError
        await session.flush()
    if configuration.status != TrainerExerciseStatus.ACTIVE:
        raise PlanExerciseUnavailableError
    return configuration


def _plan_fields(plan: TrainingPlan) -> dict[str, Any]:
    """Shared plan fields for list and detail responses."""
    return {
        "id": plan.id,
        "training_group_id": plan.training_group_id,
        "name": plan.name,
        "participant_count": plan.participant_count,
        "group_name_snapshot": plan.group_name_snapshot,
        "group_min_age_snapshot": plan.group_min_age_snapshot,
        "group_max_age_snapshot": plan.group_max_age_snapshot,
        "training_duration_snapshot": plan.training_duration_snapshot,
        "available_equipment_snapshot": _catalog_refs(
            plan.available_equipment_snapshot
        ),
        "training_types_snapshot": _catalog_refs(plan.training_types_snapshot),
        "schema_snapshot": _schema_items(plan.schema_snapshot),
        "generated_at": plan.generated_at,
    }


def _to_list_item(plan: TrainingPlan) -> PlanListItem:
    """Map an ORM plan to the list/detail shared fields."""
    return PlanListItem(**_plan_fields(plan))


def _to_detail(plan: TrainingPlan) -> PlanDetail:
    """Map an ORM plan and its exercises to the detail response."""
    return PlanDetail(
        **_plan_fields(plan),
        exercises=[
            _to_exercise(exercise)
            for exercise in sorted(plan.exercises, key=lambda item: item.position)
        ],
    )


def _to_exercise(exercise: TrainingPlanExercise) -> PlanExerciseResponse:
    """Map one immutable plan-exercise row to the API contract."""
    return PlanExerciseResponse(
        id=exercise.id,
        trainer_exercise_id=exercise.trainer_exercise_id,
        exercise_id=exercise.exercise_id,
        exercise_version_id=exercise.exercise_version_id,
        position=exercise.position,
        schema_position=exercise.schema_position,
        name_snapshot=exercise.name_snapshot,
        description_snapshot=exercise.description_snapshot,
        image_url_snapshot=exercise.image_url_snapshot,
        animation_url_snapshot=exercise.animation_url_snapshot,
        image_url_light_snapshot=exercise.image_url_light_snapshot,
        animation_url_light_snapshot=exercise.animation_url_light_snapshot,
        min_age_snapshot=exercise.min_age_snapshot,
        max_age_snapshot=exercise.max_age_snapshot,
        min_participants_snapshot=exercise.min_participants_snapshot,
        max_participants_snapshot=exercise.max_participants_snapshot,
        duration_minutes_snapshot=exercise.duration_minutes_snapshot,
        physical_difficulty_snapshot=exercise.physical_difficulty_snapshot,
        technical_difficulty_snapshot=exercise.technical_difficulty_snapshot,
        upper_body_load_snapshot=exercise.upper_body_load_snapshot,
        lower_body_load_snapshot=exercise.lower_body_load_snapshot,
        core_load_snapshot=exercise.core_load_snapshot,
        equipment_snapshot=_catalog_refs(exercise.equipment_snapshot),
        training_types_snapshot=_catalog_refs(exercise.training_types_snapshot),
        segments_snapshot=_segment_refs(exercise.segments_snapshot),
    )


def _catalog_refs(
    items: Sequence[Mapping[str, object]],
) -> list[CatalogReference]:
    """Validate JSONB catalog snapshots against the shared API contract."""
    return _CATALOG_SNAPSHOTS.validate_python(items)


def _schema_items(
    items: Sequence[Mapping[str, object]],
) -> list[PlanSchemaSnapshotItem]:
    """Validate and order the frozen group schema snapshot."""
    return sorted(
        _SCHEMA_SNAPSHOTS.validate_python(items),
        key=lambda item: item.position,
    )


def _segment_refs(
    items: Sequence[Mapping[str, object]],
) -> list[TrainingSegmentResponse]:
    """Validate JSONB segment snapshots against the shared API contract."""
    return _SEGMENT_SNAPSHOTS.validate_python(items)
