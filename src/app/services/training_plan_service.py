"""Business operations for a trainer's saved training plans."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import training_plans as training_plans_db
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

_CATALOG_SNAPSHOTS = TypeAdapter(list[CatalogReference])
_SCHEMA_SNAPSHOTS = TypeAdapter(list[PlanSchemaSnapshotItem])
_SEGMENT_SNAPSHOTS = TypeAdapter(list[TrainingSegmentResponse])


class PlanNotFoundError(Exception):
    """Raised when a plan is absent or belongs to another trainer."""


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


async def _get_owned_or_raise(
    session: AsyncSession, trainer_id: UUID, plan_id: UUID
) -> TrainingPlan:
    """Return an owned plan or raise a uniform not-found outcome."""
    plan = await training_plans_db.get_for_trainer(session, trainer_id, plan_id)
    if plan is None:
        raise PlanNotFoundError
    return plan


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
