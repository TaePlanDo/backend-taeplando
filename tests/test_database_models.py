"""PostgreSQL integration tests for the SQLAlchemy data model."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

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
    """Related records shared by the database integrity assertions."""

    user: User
    segment: TrainingSegment
    equipment: Equipment
    training_type: TrainingType
    exercise: Exercise
    trainer_exercise: TrainerExercise
    group: TrainingGroup


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
        user=user,
        segment=segment,
        equipment=equipment,
        training_type=training_type,
        exercise=exercise,
        trainer_exercise=trainer_exercise,
        group=group,
    )


async def _assert_constraints(session: AsyncSession, fixture: ModelFixture) -> None:
    """Verify representative check and foreign-key constraints."""

    async with session.begin_nested():
        invalid_group = TrainingGroup(
            trainer_id=uuid4(),
            name="Invalid age range",
            min_age=14,
            max_age=7,
            duration_minutes=60,
        )
        session.add(invalid_group)
        with pytest.raises(IntegrityError) as check_error:
            await session.flush()

    assert check_error.value.orig.sqlstate == "23514"

    async with session.begin_nested():
        missing_trainer_group = TrainingGroup(
            trainer_id=uuid4(),
            name="Missing trainer",
            min_age=7,
            max_age=14,
            duration_minutes=60,
        )
        session.add(missing_trainer_group)
        with pytest.raises(IntegrityError) as foreign_key_error:
            await session.flush()

    assert foreign_key_error.value.orig.sqlstate == "23503"

    async with session.begin_nested():
        invalid_duration_exercise = TrainerExercise(
            trainer=fixture.user,
            exercise=Exercise(
                owner=fixture.user,
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
        )
        session.add(invalid_duration_exercise)
        with pytest.raises(IntegrityError) as duration_error:
            await session.flush()

    assert duration_error.value.orig.sqlstate == "23514"

    async with session.begin_nested():
        invalid_schema_item = TrainingGroupSchemaItem(
            training_group=fixture.group,
            segment=fixture.segment,
            percentage=101,
            position=2,
        )
        session.add(invalid_schema_item)
        with pytest.raises(IntegrityError) as percentage_error:
            await session.flush()

    assert percentage_error.value.orig.sqlstate == "23514"


async def _assert_unique_constraints(
    session: AsyncSession, fixture: ModelFixture
) -> None:
    """Verify unique constraints and partial indexes used by the catalog."""

    async with session.begin_nested():
        duplicate_trainer_exercise = TrainerExercise(
            trainer=fixture.user,
            exercise=fixture.exercise,
            status=TrainerExerciseStatus.ACTIVE,
            min_age=7,
            max_age=14,
            min_participants=2,
            max_participants=20,
            duration_minutes=10,
        )
        session.add(duplicate_trainer_exercise)
        with pytest.raises(IntegrityError) as trainer_exercise_error:
            await session.flush()

    assert trainer_exercise_error.value.orig.sqlstate == "23505"

    global_equipment_name = f"Global equipment {uuid4()}"
    session.add(
        Equipment(
            name=global_equipment_name,
            visibility=CatalogVisibility.GLOBAL,
        )
    )
    await session.flush()
    async with session.begin_nested():
        session.add(
            Equipment(
                name=global_equipment_name.upper(),
                visibility=CatalogVisibility.GLOBAL,
            )
        )
        with pytest.raises(IntegrityError) as equipment_error:
            await session.flush()

    assert equipment_error.value.orig.sqlstate == "23505"

    global_training_type_name = f"Global training type {uuid4()}"
    session.add(
        TrainingType(
            name=global_training_type_name,
            visibility=CatalogVisibility.GLOBAL,
        )
    )
    await session.flush()
    async with session.begin_nested():
        session.add(
            TrainingType(
                name=global_training_type_name.upper(),
                visibility=CatalogVisibility.GLOBAL,
            )
        )
        with pytest.raises(IntegrityError) as training_type_error:
            await session.flush()

    assert training_type_error.value.orig.sqlstate == "23505"


async def _assert_jsonb_snapshots(session: AsyncSession, fixture: ModelFixture) -> None:
    """Persist and reload the immutable JSONB snapshots of a training plan."""

    equipment_snapshot = [{"id": str(fixture.equipment.id), "name": "Test target"}]
    training_type_snapshot = [
        {"id": str(fixture.training_type.id), "name": "Test technique"}
    ]
    schema_snapshot = [
        {
            "position": 1,
            "segment_id": fixture.segment.id,
            "code": fixture.segment.code,
            "name": fixture.segment.name,
            "percentage": 100,
        }
    ]
    plan = TrainingPlan(
        trainer=fixture.user,
        training_group=fixture.group,
        participant_count=10,
        name="Model test plan",
        group_name_snapshot=fixture.group.name,
        group_min_age_snapshot=fixture.group.min_age,
        group_max_age_snapshot=fixture.group.max_age,
        training_duration_snapshot=fixture.group.duration_minutes,
        available_equipment_snapshot=equipment_snapshot,
        training_types_snapshot=training_type_snapshot,
        schema_snapshot=schema_snapshot,
    )
    plan_exercise = TrainingPlanExercise(
        training_plan=plan,
        trainer_exercise=fixture.trainer_exercise,
        exercise=fixture.exercise,
        position=1,
        schema_position=1,
        name_snapshot=fixture.exercise.name,
        description_snapshot=fixture.exercise.description,
        min_age_snapshot=7,
        max_age_snapshot=14,
        min_participants_snapshot=2,
        max_participants_snapshot=20,
        duration_minutes_snapshot=10,
        equipment_snapshot=equipment_snapshot,
        training_types_snapshot=training_type_snapshot,
        segments_snapshot=[
            {
                "id": fixture.segment.id,
                "code": fixture.segment.code,
                "name": fixture.segment.name,
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
            "id": fixture.segment.id,
            "code": fixture.segment.code,
            "name": fixture.segment.name,
        }
    ]
