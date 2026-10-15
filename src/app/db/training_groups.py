"""Database queries for trainer-owned groups."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from app.models.catalogs import TrainingSegment
from app.models.training import (
    TrainingGroup,
    TrainingGroupSchemaItem,
    TrainingPlan,
    TrainingPlanExercise,
)


class GroupPage(NamedTuple):
    items: list[TrainingGroup]
    total: int


def _group_response_options() -> tuple[LoaderOption, ...]:
    """Eager-load options shared by the response-building queries."""
    return (
        selectinload(TrainingGroup.schema_items).selectinload(
            TrainingGroupSchemaItem.segment
        ),
        selectinload(TrainingGroup.training_plans).load_only(TrainingPlan.id),
    )


def _group_response_query() -> Select[TrainingGroup]:
    """Load a group with all relations needed by the public API response."""
    return select(TrainingGroup).options(*_group_response_options())


def _group_delete_query() -> Select[TrainingGroup]:
    """Load only the dependent rows required for ORM cascade deletion."""
    return select(TrainingGroup).options(
        selectinload(TrainingGroup.schema_items).load_only(TrainingGroupSchemaItem.id),
        selectinload(TrainingGroup.training_plans).load_only(TrainingPlan.id),
        selectinload(TrainingGroup.training_plans)
        .selectinload(TrainingPlan.exercises)
        .load_only(TrainingPlanExercise.id),
    )


def _trainer_filters(
    trainer_id: UUID,
    *,
    duration_minutes: int | None = None,
    min_age: int = 0,
    max_age: int = 99,
) -> list[ColumnElement[bool]]:
    """Build the filter conditions applied to a trainer's group queries."""
    filters: list[ColumnElement[bool]] = [
        TrainingGroup.trainer_id == trainer_id,
        TrainingGroup.min_age >= min_age,
        TrainingGroup.max_age <= max_age,
    ]
    if duration_minutes is not None:
        filters.append(TrainingGroup.duration_minutes == duration_minutes)
    return filters


async def list_for_trainer(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    duration_minutes: int | None = None,
    min_age: int = 0,
    max_age: int = 99,
    offset: int = 0,
    limit: int = 20,
) -> GroupPage:
    """Return one stable page of a trainer's groups and the matching total."""
    filters = _trainer_filters(
        trainer_id,
        duration_minutes=duration_minutes,
        min_age=min_age,
        max_age=max_age,
    )
    statement = (
        select(TrainingGroup, func.count().over())
        .options(*_group_response_options())
        .where(*filters)
        .order_by(TrainingGroup.name, TrainingGroup.id)
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(statement)
    rows = result.unique().all()
    if rows:
        return GroupPage(items=[group for group, _ in rows], total=rows[0][1])
    if offset == 0:
        return GroupPage(items=[], total=0)
    return GroupPage(items=[], total=await _count_matching(session, filters))


async def _count_matching(
    session: AsyncSession, filters: list[ColumnElement[bool]]
) -> int:
    """Count the groups matching the given filters."""
    result = await session.execute(
        select(func.count()).select_from(TrainingGroup).where(*filters)
    )
    return result.scalar_one()


async def get_for_trainer(
    session: AsyncSession, trainer_id: UUID, group_id: UUID
) -> TrainingGroup | None:
    """Find a group only when it belongs to the requesting trainer."""
    result = await session.execute(
        _group_response_query().where(
            TrainingGroup.id == group_id,
            TrainingGroup.trainer_id == trainer_id,
        )
    )
    return result.scalar_one_or_none()


async def list_for_deletion(
    session: AsyncSession, trainer_id: UUID
) -> list[TrainingGroup]:
    """Return a trainer's groups with only the rows their cascade needs."""
    result = await session.execute(
        _group_delete_query().where(TrainingGroup.trainer_id == trainer_id)
    )
    return list(result.scalars().unique())


async def get_for_deletion(
    session: AsyncSession, trainer_id: UUID, group_id: UUID
) -> TrainingGroup | None:
    """Find one owned group with only the rows its cascade needs."""
    result = await session.execute(
        _group_delete_query().where(
            TrainingGroup.id == group_id,
            TrainingGroup.trainer_id == trainer_id,
        )
    )
    return result.scalar_one_or_none()


async def get_training_segment_by_code(
    session: AsyncSession, code: str
) -> TrainingSegment | None:
    """Return one fixed training-schema segment by its immutable code."""
    result = await session.execute(
        select(TrainingSegment).where(TrainingSegment.code == code)
    )
    return result.scalar_one_or_none()
