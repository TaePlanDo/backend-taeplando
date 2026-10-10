"""Business operations for a trainer's training groups."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import training_groups as training_groups_db
from app.models.catalogs import TrainingSegment
from app.models.training import TrainingGroup, TrainingGroupSchemaItem
from app.schemas.training import (
    TrainingGroupResponse,
    TrainingGroupSchemaItemResponse,
    TrainingGroupWrite,
)

MAIN_SEGMENT_CODE = "MAIN"


class TrainingGroupNotFoundError(Exception):
    """Raised when a group is absent or belongs to another trainer."""


async def list_training_groups(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    duration_minutes: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
) -> list[TrainingGroupResponse]:
    """List the groups owned by one trainer."""
    groups = await training_groups_db.list_for_trainer(
        session,
        trainer_id,
        duration_minutes=duration_minutes,
        min_age=min_age,
        max_age=max_age,
    )
    return [_to_response(group) for group in groups]


async def get_training_group(
    session: AsyncSession, trainer_id: UUID, group_id: UUID
) -> TrainingGroupResponse:
    """Return a single owned group, without disclosing other trainers' data."""
    group = await _get_owned_group_or_raise(session, trainer_id, group_id)
    return _to_response(group)


async def create_training_group(
    session: AsyncSession, trainer_id: UUID, payload: TrainingGroupWrite
) -> TrainingGroupResponse:
    """Create a group with its required 100% main-part starting schema."""
    main_segment = await _get_main_segment(session)
    group = TrainingGroup(
        trainer_id=trainer_id,
        **payload.model_dump(),
        schema_items=[
            TrainingGroupSchemaItem(
                segment=main_segment,
                percentage=100,
                position=1,
            )
        ],
    )
    session.add(group)
    await session.commit()
    return _to_response(group)


async def put_training_group(
    session: AsyncSession,
    trainer_id: UUID,
    group_id: UUID,
    payload: TrainingGroupWrite,
) -> TrainingGroupResponse:
    """Replace all editable fields of a group owned by the current trainer."""
    group = await _get_owned_group_or_raise(session, trainer_id, group_id)
    group.name = payload.name
    group.min_age = payload.min_age
    group.max_age = payload.max_age
    group.duration_minutes = payload.duration_minutes
    await session.commit()
    return _to_response(group)


async def delete_training_group(
    session: AsyncSession, trainer_id: UUID, group_id: UUID
) -> None:
    """Delete an owned group together with its dependent historical plans."""
    group = await _get_owned_group_or_raise(session, trainer_id, group_id)
    await session.delete(group)
    await session.commit()


async def delete_all_trainer_training_groups(
    session: AsyncSession, trainer_id: UUID
) -> None:
    """Delete all of a trainer's groups and their dependent historical plans."""
    groups = await training_groups_db.list_for_trainer(session, trainer_id)
    for group in groups:
        await session.delete(group)
    await session.commit()


async def _get_owned_group_or_raise(
    session: AsyncSession, trainer_id: UUID, group_id: UUID
) -> TrainingGroup:
    """Return an owned group or raise a uniform not-found outcome."""
    group = await training_groups_db.get_for_trainer(session, trainer_id, group_id)
    if group is None:
        raise TrainingGroupNotFoundError
    return group


async def _get_main_segment(session: AsyncSession) -> TrainingSegment:
    """Resolve the fixed dictionary item used by every new group's schema."""
    segment = await training_groups_db.get_training_segment_by_code(
        session, MAIN_SEGMENT_CODE
    )
    if segment is None:
        raise RuntimeError("The MAIN training segment has not been seeded")
    return segment


def _to_response(group: TrainingGroup) -> TrainingGroupResponse:
    """Map an ORM group to the complete API contract."""
    return TrainingGroupResponse(
        id=group.id,
        trainer_id=group.trainer_id,
        name=group.name,
        min_age=group.min_age,
        max_age=group.max_age,
        duration_minutes=group.duration_minutes,
        created_at=group.created_at,
        updated_at=group.updated_at,
        plan_ids=sorted(plan.id for plan in group.training_plans),
        schema_items=[
            TrainingGroupSchemaItemResponse(
                segment_id=item.segment.id,
                segment_code=item.segment.code,
                segment_name=item.segment.name,
                percentage=item.percentage,
                position=item.position,
            )
            for item in sorted(group.schema_items, key=lambda item: item.position)
        ],
    )
