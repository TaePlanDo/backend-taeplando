"""Database queries for a trainer's saved training plans."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, SQLColumnExpression, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.sql_filters import ilike_contains
from app.models.training import TrainingPlan
from app.schemas.training_plans import TrainingPlanListFilters


class PlanPage(NamedTuple):
    items: list[TrainingPlan]
    total: int


def _jsonb_any_of_ids(
    column: SQLColumnExpression[object], ids: list[UUID]
) -> ColumnElement[bool]:
    """Match when the JSONB catalog snapshot contains at least one requested id."""
    return or_(*(column.contains([{"id": str(item_id)}]) for item_id in ids))


def _append_bounds(
    predicates: list[ColumnElement[bool]],
    column: SQLColumnExpression[int],
    *,
    lower: int | None,
    upper: int | None,
) -> None:
    """Append inclusive scalar lower/upper bounds when either side is set."""
    if lower is not None:
        predicates.append(column >= lower)
    if upper is not None:
        predicates.append(column <= upper)


def _list_filters(
    trainer_id: UUID, filters: TrainingPlanListFilters
) -> list[ColumnElement[bool]]:
    """Build the filter conditions applied to a trainer's plan list."""
    predicates: list[ColumnElement[bool]] = [TrainingPlan.trainer_id == trainer_id]
    if filters.name is not None:
        predicates.append(ilike_contains(TrainingPlan.name, filters.name))
    if filters.min_age is not None:
        predicates.append(TrainingPlan.group_max_age_snapshot >= filters.min_age)
    if filters.max_age is not None:
        predicates.append(TrainingPlan.group_min_age_snapshot <= filters.max_age)
    _append_bounds(
        predicates,
        TrainingPlan.participant_count,
        lower=filters.min_participants,
        upper=filters.max_participants,
    )
    _append_bounds(
        predicates,
        TrainingPlan.training_duration_snapshot,
        lower=filters.min_duration,
        upper=filters.max_duration,
    )
    if filters.equipment_ids:
        predicates.append(
            _jsonb_any_of_ids(
                TrainingPlan.available_equipment_snapshot, filters.equipment_ids
            )
        )
    if filters.training_type_ids:
        predicates.append(
            _jsonb_any_of_ids(
                TrainingPlan.training_types_snapshot, filters.training_type_ids
            )
        )
    if filters.training_group_ids:
        predicates.append(
            TrainingPlan.training_group_id.in_(filters.training_group_ids)
        )
    return predicates


async def list_for_trainer(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    filters: TrainingPlanListFilters,
    offset: int = 0,
    limit: int = 20,
) -> PlanPage:
    """Return one newest-first page of a trainer's plans and the matching total."""
    predicates = _list_filters(trainer_id, filters)
    statement = (
        select(TrainingPlan, func.count().over())
        .where(*predicates)
        .order_by(TrainingPlan.generated_at.desc(), TrainingPlan.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(statement)
    rows = result.all()
    if rows:
        return PlanPage(items=[plan for plan, _ in rows], total=rows[0][1])
    if offset == 0:
        return PlanPage(items=[], total=0)
    return PlanPage(items=[], total=await _count_matching(session, predicates))


async def _count_matching(
    session: AsyncSession, predicates: list[ColumnElement[bool]]
) -> int:
    """Count the plans matching the given filters."""
    result = await session.execute(
        select(func.count()).select_from(TrainingPlan).where(*predicates)
    )
    return result.scalar_one()


async def get_for_trainer(
    session: AsyncSession, trainer_id: UUID, plan_id: UUID
) -> TrainingPlan | None:
    """Find an owned plan with exercise snapshots for detail and delete."""
    result = await session.execute(
        select(TrainingPlan)
        .where(TrainingPlan.id == plan_id, TrainingPlan.trainer_id == trainer_id)
        .options(selectinload(TrainingPlan.exercises))
    )
    return result.scalar_one_or_none()
