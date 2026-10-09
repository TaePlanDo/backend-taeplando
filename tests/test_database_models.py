"""PostgreSQL integration tests for the SQLAlchemy data model."""

from __future__ import annotations

import asyncio
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
from app.models.training import TrainingGroup, TrainingGroupSchemaItem
from app.models.users import User


def test_database_models_relationships_and_constraints() -> None:
    """Persist related models and reject invalid database records."""

    asyncio.run(_assert_database_models_relationships_and_constraints())


async def _assert_database_models_relationships_and_constraints() -> None:
    """Execute the database integration assertions on one event loop."""

    try:
        async with get_session_factory()() as session:
            await _assert_relationships(session)
            await _assert_constraints(session)
    finally:
        await dispose_engine()


async def _assert_relationships(session: AsyncSession) -> None:
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
    assert [item.name for item in stored_exercise.training_types] == [
        "Test technique"
    ]
    assert [item.code for item in stored_exercise.segments] == ["TEST_SEGMENT"]
    assert schema_item.training_group_id == group.id


async def _assert_constraints(session: AsyncSession) -> None:
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
