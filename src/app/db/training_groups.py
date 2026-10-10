"""Database queries for trainer-owned groups."""

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalogs import TrainingSegment
from app.models.training import (
    TrainingGroup,
    TrainingGroupSchemaItem,
    TrainingPlan,
    TrainingPlanExercise,
)


def _group_response_query() -> Select[TrainingGroup]:
    """Load a group with all relations needed by the public API response."""
    return select(TrainingGroup).options(
        selectinload(TrainingGroup.schema_items).selectinload(
            TrainingGroupSchemaItem.segment
        ),
        selectinload(TrainingGroup.training_plans).load_only(TrainingPlan.id),
    )


def _group_delete_query() -> Select[TrainingGroup]:
    """Load only the dependent rows required for ORM cascade deletion."""
    return select(TrainingGroup).options(
        selectinload(TrainingGroup.schema_items).load_only(TrainingGroupSchemaItem.id),
        selectinload(TrainingGroup.training_plans).load_only(TrainingPlan.id),
        selectinload(TrainingGroup.training_plans)
        .selectinload(TrainingPlan.exercises)
        .load_only(TrainingPlanExercise.id),
    )


async def list_for_trainer(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    duration_minutes: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
) -> list[TrainingGroup]:
    """Return only the requesting trainer's groups in a stable display order."""
    statement = _group_response_query().where(TrainingGroup.trainer_id == trainer_id)
    if duration_minutes is not None:
        statement = statement.where(TrainingGroup.duration_minutes == duration_minutes)
    if min_age is not None:
        statement = statement.where(TrainingGroup.min_age == min_age)
    if max_age is not None:
        statement = statement.where(TrainingGroup.max_age == max_age)
    result = await session.execute(
        statement.order_by(TrainingGroup.name, TrainingGroup.id)
    )
    return list(result.scalars().unique())


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
