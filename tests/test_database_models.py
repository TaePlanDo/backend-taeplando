"""PostgreSQL integration tests for the SQLAlchemy data model."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, TypeGuard
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import dispose_engine, get_session_factory
from app.models.catalogs import Equipment, TrainingSegment, TrainingType
from app.models.enums import (
    AuthMethod,
    CatalogVisibility,
    ExerciseScope,
    TrainerExerciseStatus,
)
from app.models.exercises import Exercise, TrainerExercise
from app.models.training import (
    TrainingGroup,
    TrainingGroupSchemaItem,
    TrainingPlan,
    TrainingPlanExercise,
)
from app.models.users import User


@dataclass(frozen=True)
class ModelFixture:
    """Persisted values shared by the database integrity assertions."""

    trainer_id: UUID
    segment_id: int
    segment_code: str
    segment_name: str
    equipment_id: UUID
    training_type_id: UUID
    exercise_id: UUID
    trainer_exercise_id: UUID
    group_id: UUID
    group_name: str
    group_min_age: int
    group_max_age: int
    group_duration_minutes: int


class SqlStateError(Protocol):
    """Database error shape exposed by PostgreSQL drivers."""

    sqlstate: str


def test_database_models_relationships_and_constraints() -> None:
    """Persist related models and reject invalid database records."""

    asyncio.run(_assert_database_models_relationships_and_constraints())


async def _assert_database_models_relationships_and_constraints() -> None:
    """Execute the database integration assertions on one event loop."""

    try:
        async with get_session_factory()() as session:
            fixture = await _assert_relationships(session)
            await _assert_jsonb_snapshots(session, fixture)
            await _assert_constraints(session, fixture)
            await _assert_unique_constraints(session, fixture)
    finally:
        await dispose_engine()


async def _assert_relationships(session: AsyncSession) -> ModelFixture:
    """Store and read the main ORM relationships through PostgreSQL."""

    user = User(
        email=f"model-test-{uuid4()}@example.test",
        full_name="Model test trainer",
        auth_method=AuthMethod.GOOGLE,
        oauth_subject=f"model-test-{uuid4()}",
    )
    segment = TrainingSegment(id=32000, code="TEST_SEGMENT", name="Test segment")
    equipment = Equipment(
        owner=user,
        name="Test target",
        visibility=CatalogVisibility.LOCAL,
    )
    training_type = TrainingType(
        owner=user,
        name="Test technique",
        visibility=CatalogVisibility.LOCAL,
    )
    exercise = Exercise(
        owner=user,
        scope=ExerciseScope.PRIVATE,
        name="Test exercise",
        description="Exercise used only by the model integration test.",
    )
    trainer_exercise = TrainerExercise(
        trainer=user,
        exercise=exercise,
        status=TrainerExerciseStatus.ACTIVE,
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
        equipment=[equipment],
        training_types=[training_type],
        segments=[segment],
    )
    group = TrainingGroup(
        trainer=user,
        name="Model test group",
        min_age=7,
        max_age=14,
        duration_minutes=60,
    )
    schema_item = TrainingGroupSchemaItem(
        training_group=group,
        segment=segment,
        percentage=100,
        position=1,
    )
    session.add_all(
        [
            user,
            segment,
            equipment,
            training_type,
            exercise,
            trainer_exercise,
            group,
            schema_item,
        ]
    )
    await session.flush()

    result = await session.execute(
        select(TrainerExercise)
        .where(TrainerExercise.id == trainer_exercise.id)
        .options(
            selectinload(TrainerExercise.equipment),
            selectinload(TrainerExercise.training_types),
            selectinload(TrainerExercise.segments),
        )
    )
    stored_exercise = result.scalar_one()

    assert [item.name for item in stored_exercise.equipment] == ["Test target"]
    assert [item.name for item in stored_exercise.training_types] == ["Test technique"]
    assert [item.code for item in stored_exercise.segments] == ["TEST_SEGMENT"]
    assert schema_item.training_group_id == group.id

    return ModelFixture(
        trainer_id=user.id,
        segment_id=segment.id,
        segment_code=segment.code,
        segment_name=segment.name,
        equipment_id=equipment.id,
        training_type_id=training_type.id,
        exercise_id=exercise.id,
        trainer_exercise_id=trainer_exercise.id,
        group_id=group.id,
        group_name=group.name,
        group_min_age=group.min_age,
        group_max_age=group.max_age,
        group_duration_minutes=group.duration_minutes,
    )


async def _assert_constraints(session: AsyncSession, fixture: ModelFixture) -> None:
    """Verify representative check and foreign-key constraints."""

    await _assert_integrity_error(
        session,
        TrainingGroup(
            trainer_id=uuid4(),
            name="Invalid age range",
            min_age=14,
            max_age=7,
            duration_minutes=60,
        ),
        "23514",
    )
    await _assert_integrity_error(
        session,
        TrainingGroup(
            trainer_id=uuid4(),
            name="Missing trainer",
            min_age=7,
            max_age=14,
            duration_minutes=60,
        ),
        "23503",
    )
    await _assert_integrity_error(
        session,
        TrainerExercise(
            trainer_id=fixture.trainer_id,
            exercise=Exercise(
                owner_user_id=fixture.trainer_id,
                scope=ExerciseScope.PRIVATE,
                name="Invalid duration exercise",
                description="Used to test a duration constraint.",
            ),
            status=TrainerExerciseStatus.ACTIVE,
            min_age=7,
            max_age=14,
            min_participants=2,
            max_participants=20,
            duration_minutes=0,
        ),
        "23514",
    )
    await _assert_integrity_error(
        session,
        TrainingGroupSchemaItem(
            training_group_id=fixture.group_id,
            segment_id=fixture.segment_id,
            percentage=101,
            position=2,
        ),
        "23514",
    )


async def _assert_unique_constraints(
    session: AsyncSession, fixture: ModelFixture
) -> None:
    """Verify unique constraints and partial indexes used by the catalog."""

    await _assert_integrity_error(
        session,
        TrainerExercise(
            trainer_id=fixture.trainer_id,
            exercise_id=fixture.exercise_id,
            status=TrainerExerciseStatus.ACTIVE,
            min_age=7,
            max_age=14,
            min_participants=2,
            max_participants=20,
            duration_minutes=10,
        ),
        "23505",
    )
    await _assert_case_insensitive_global_catalog_uniqueness(session, Equipment)
    await _assert_case_insensitive_global_catalog_uniqueness(session, TrainingType)


async def _assert_integrity_error(
    session: AsyncSession, record: object, expected_sqlstate: str
) -> None:
    """Assert that one insert fails with the expected PostgreSQL SQLSTATE."""

    async with session.begin_nested():
        session.add(record)
        with pytest.raises(IntegrityError) as error:
            await session.flush()

    original_error = error.value.orig
    assert _has_sqlstate(original_error)
    assert original_error.sqlstate == expected_sqlstate


def _has_sqlstate(error: BaseException | None) -> TypeGuard[SqlStateError]:
    """Narrow a driver exception to PostgreSQL's SQLSTATE error contract."""

    return error is not None and isinstance(getattr(error, "sqlstate", None), str)


async def _assert_case_insensitive_global_catalog_uniqueness(
    session: AsyncSession, catalog_model: type[Equipment] | type[TrainingType]
) -> None:
    """Verify the case-insensitive unique index of one global catalog."""

    name = f"Global catalog {uuid4()}"
    session.add(catalog_model(name=name, visibility=CatalogVisibility.GLOBAL))
    await session.flush()
    await _assert_integrity_error(
        session,
        catalog_model(name=name.upper(), visibility=CatalogVisibility.GLOBAL),
        "23505",
    )


async def _assert_jsonb_snapshots(session: AsyncSession, fixture: ModelFixture) -> None:
    """Persist and reload the immutable JSONB snapshots of a training plan."""

    equipment_snapshot = [{"id": str(fixture.equipment_id), "name": "Test target"}]
    training_type_snapshot = [
        {"id": str(fixture.training_type_id), "name": "Test technique"}
    ]
    schema_snapshot = [
        {
            "position": 1,
            "segment_id": fixture.segment_id,
            "code": fixture.segment_code,
            "name": fixture.segment_name,
            "percentage": 100,
        }
    ]
    plan = TrainingPlan(
        trainer_id=fixture.trainer_id,
        training_group_id=fixture.group_id,
        participant_count=10,
        name="Model test plan",
        group_name_snapshot=fixture.group_name,
        group_min_age_snapshot=fixture.group_min_age,
        group_max_age_snapshot=fixture.group_max_age,
        training_duration_snapshot=fixture.group_duration_minutes,
        available_equipment_snapshot=equipment_snapshot,
        training_types_snapshot=training_type_snapshot,
        schema_snapshot=schema_snapshot,
    )
    plan_exercise = TrainingPlanExercise(
        training_plan=plan,
        trainer_exercise_id=fixture.trainer_exercise_id,
        exercise_id=fixture.exercise_id,
        position=1,
        schema_position=1,
        name_snapshot="Test exercise",
        description_snapshot="Exercise used only by the model integration test.",
        min_age_snapshot=7,
        max_age_snapshot=14,
        min_participants_snapshot=2,
        max_participants_snapshot=20,
        duration_minutes_snapshot=10,
        equipment_snapshot=equipment_snapshot,
        training_types_snapshot=training_type_snapshot,
        segments_snapshot=[
            {
                "id": fixture.segment_id,
                "code": fixture.segment_code,
                "name": fixture.segment_name,
            }
        ],
    )
    session.add_all([plan, plan_exercise])
    await session.flush()
    await session.refresh(plan)
    await session.refresh(plan_exercise)

    assert plan.available_equipment_snapshot == equipment_snapshot
    assert plan.training_types_snapshot == training_type_snapshot
    assert plan.schema_snapshot == schema_snapshot
    assert plan_exercise.segments_snapshot == [
        {
            "id": fixture.segment_id,
            "code": fixture.segment_code,
            "name": fixture.segment_name,
        }
    ]
