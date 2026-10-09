"""Integration test for the SQLAlchemy model relationships and constraints."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import dispose_engine, get_engine
from app.models import Base
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


def test_database_models_relationships_and_constraints() -> None:
    """Persist related models and reject invalid database records."""

    asyncio.run(_test_database_models_relationships_and_constraints())


async def _test_database_models_relationships_and_constraints() -> None:
    """Use a temporary schema transaction so the test leaves no database state."""

    try:
        async with get_engine().connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.run_sync(Base.metadata.create_all)
                async with AsyncSession(
                    connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    await _assert_relationships_and_snapshots(session)
                    await _assert_constraints(session)
            finally:
                await transaction.rollback()
    finally:
        await dispose_engine()


async def _assert_relationships_and_snapshots(session: AsyncSession) -> None:
    """Store a minimal graph and reload its relations and historical snapshots."""

    trainer = User(
        email=f"model-test-{uuid4()}@example.test",
        full_name="Model test trainer",
        auth_method=AuthMethod.GOOGLE,
        oauth_subject=f"model-test-{uuid4()}",
    )
    segment = TrainingSegment(id=32000, code="TEST_SEGMENT", name="Test segment")
    equipment = Equipment(
        owner=trainer,
        name="Test target",
        visibility=CatalogVisibility.LOCAL,
    )
    training_type = TrainingType(
        owner=trainer,
        name="Test technique",
        visibility=CatalogVisibility.LOCAL,
    )
    exercise = Exercise(
        owner=trainer,
        scope=ExerciseScope.PRIVATE,
        name="Test exercise",
        description="Exercise used only by the model integration test.",
    )
    trainer_exercise = TrainerExercise(
        trainer=trainer,
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
        trainer=trainer,
        name="Model test group",
        min_age=7,
        max_age=14,
        duration_minutes=60,
    )
    TrainingGroupSchemaItem(
        training_group=group,
        segment=segment,
        percentage=100,
        position=1,
    )
    equipment_snapshot = [{"id": str(equipment.id), "name": equipment.name}]
    training_type_snapshot = [{"id": str(training_type.id), "name": training_type.name}]
    schema_snapshot = [
        {
            "position": 1,
            "segment_id": segment.id,
            "code": segment.code,
            "name": segment.name,
            "percentage": 100,
        }
    ]
    plan = TrainingPlan(
        trainer=trainer,
        training_group=group,
        participant_count=10,
        name="Model test plan",
        group_name_snapshot=group.name,
        group_min_age_snapshot=group.min_age,
        group_max_age_snapshot=group.max_age,
        training_duration_snapshot=group.duration_minutes,
        available_equipment_snapshot=equipment_snapshot,
        training_types_snapshot=training_type_snapshot,
        schema_snapshot=schema_snapshot,
    )
    TrainingPlanExercise(
        training_plan=plan,
        trainer_exercise=trainer_exercise,
        exercise=exercise,
        position=1,
        schema_position=1,
        name_snapshot=exercise.name,
        description_snapshot=exercise.description,
        min_age_snapshot=7,
        max_age_snapshot=14,
        min_participants_snapshot=2,
        max_participants_snapshot=20,
        duration_minutes_snapshot=10,
        equipment_snapshot=equipment_snapshot,
        training_types_snapshot=training_type_snapshot,
        segments_snapshot=[
            {"id": segment.id, "code": segment.code, "name": segment.name}
        ],
    )
    session.add_all([trainer_exercise, group, plan])
    await session.flush()

    stored_exercise = (
        await session.execute(
            select(TrainerExercise)
            .where(TrainerExercise.id == trainer_exercise.id)
            .options(
                selectinload(TrainerExercise.equipment),
                selectinload(TrainerExercise.training_types),
                selectinload(TrainerExercise.segments),
            )
        )
    ).scalar_one()

    assert [item.name for item in stored_exercise.equipment] == [equipment.name]
    assert [item.name for item in stored_exercise.training_types] == [
        training_type.name
    ]
    assert [item.code for item in stored_exercise.segments] == [segment.code]
    assert plan.schema_snapshot == schema_snapshot
    assert plan.exercises[0].segments_snapshot == [
        {"id": segment.id, "code": segment.code, "name": segment.name}
    ]


async def _assert_constraints(session: AsyncSession) -> None:
    """Check one representative range and foreign-key constraint."""

    await _assert_rejected(
        session,
        TrainingGroup(
            trainer_id=uuid4(),
            name="Invalid age range",
            min_age=14,
            max_age=7,
            duration_minutes=60,
        ),
    )
    await _assert_rejected(
        session,
        TrainingGroup(
            trainer_id=uuid4(),
            name="Missing trainer",
            min_age=7,
            max_age=14,
            duration_minutes=60,
        ),
    )


async def _assert_rejected(session: AsyncSession, record: object) -> None:
    """Confirm one invalid record is rejected without affecting later assertions."""

    async with session.begin_nested():
        session.add(record)
        with pytest.raises(IntegrityError):
            await session.flush()
