"""Seed the fixed system data required by the application."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import dispose_engine, get_session_factory
from app.models.associations import (
    trainer_exercise_equipment,
    trainer_exercise_segments,
    trainer_exercise_training_types,
)
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


class TrainingSegmentSeed(TypedDict):
    """One immutable entry of the system training-segment dictionary."""

    id: int
    code: str
    name: str


SYSTEM_TRAINING_SEGMENTS: Sequence[TrainingSegmentSeed] = (
    {"id": 1, "code": "WARMUP", "name": "Rozgrzewka"},
    {"id": 2, "code": "GAME", "name": "Zabawa"},
    {"id": 3, "code": "MAIN", "name": "Część główna"},
    {"id": 4, "code": "COOLDOWN", "name": "Wyciszenie"},
)

# Fixed identifiers make repeated seed runs idempotent and preserve relations.
DEMO_TRAINER_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a01")
DEMO_EQUIPMENT_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a02")
DEMO_TRAINING_TYPE_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a03")
DEMO_EXERCISE_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a04")
DEMO_TRAINER_EXERCISE_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a05")
DEMO_TRAINING_GROUP_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a06")
DEMO_WARMUP_SCHEMA_ITEM_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a07")
DEMO_MAIN_SCHEMA_ITEM_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a08")
DEMO_COOLDOWN_SCHEMA_ITEM_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a09")
DEMO_TRAINING_PLAN_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a10")
DEMO_PLAN_EXERCISE_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a11")
# Local development only. Plain-text password: Demo123!
DEMO_TRAINER_PASSWORD_HASH = (
    "$2b$12$lKh3KdhbwN93vZ0SYbtWFuO15sk0Y.H64xZaP3v6hGaaqqKe2S.Mm"
)


async def seed_training_segments(session: AsyncSession) -> None:
    """Insert or restore the fixed training-segment dictionary."""

    statement = insert(TrainingSegment).values(list(SYSTEM_TRAINING_SEGMENTS))
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[TrainingSegment.id],
            set_={
                "code": statement.excluded.code,
                "name": statement.excluded.name,
            },
        )
    )


async def insert_if_missing(
    session: AsyncSession, table: Any, values: dict[str, object]
) -> None:
    """Insert one deterministic seed record without replacing existing data."""

    statement = insert(table).values(values)
    await session.execute(statement.on_conflict_do_nothing(index_elements=[table.c.id]))


async def seed_demo_data(session: AsyncSession) -> None:
    """Insert one connected trainer, group, exercise, and example plan."""

    demo_trainer = insert(User).values(
        id=DEMO_TRAINER_ID,
        email="demo.trener@gmail.com",
        full_name="Trener demonstracyjny",
        auth_method=AuthMethod.LOCAL,
        password_hash=DEMO_TRAINER_PASSWORD_HASH,
    )
    await session.execute(
        demo_trainer.on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "email": demo_trainer.excluded.email,
                "full_name": demo_trainer.excluded.full_name,
                "auth_method": demo_trainer.excluded.auth_method,
                "password_hash": demo_trainer.excluded.password_hash,
                "oauth_subject": None,
            },
        )
    )
    await insert_if_missing(
        session,
        Equipment.__table__,
        {
            "id": DEMO_EQUIPMENT_ID,
            "owner_user_id": DEMO_TRAINER_ID,
            "name": "Tarcza treningowa",
            "visibility": CatalogVisibility.LOCAL,
        },
    )
    await insert_if_missing(
        session,
        TrainingType.__table__,
        {
            "id": DEMO_TRAINING_TYPE_ID,
            "owner_user_id": DEMO_TRAINER_ID,
            "name": "Technika",
            "visibility": CatalogVisibility.LOCAL,
        },
    )
    await insert_if_missing(
        session,
        Exercise.__table__,
        {
            "id": DEMO_EXERCISE_ID,
            "owner_user_id": DEMO_TRAINER_ID,
            "scope": ExerciseScope.PRIVATE,
            "name": "Ap chagi na tarczę",
            "description": "Kopnięcia frontalne na tarczę trzymaną przez partnera.",
        },
    )
    await insert_if_missing(
        session,
        TrainerExercise.__table__,
        {
            "id": DEMO_TRAINER_EXERCISE_ID,
            "trainer_id": DEMO_TRAINER_ID,
            "exercise_id": DEMO_EXERCISE_ID,
            "status": TrainerExerciseStatus.ACTIVE,
            "min_age": 7,
            "max_age": 14,
            "min_participants": 2,
            "max_participants": 20,
            "duration_minutes": 10,
        },
    )
    await session.execute(
        insert(trainer_exercise_equipment)
        .values(
            trainer_exercise_id=DEMO_TRAINER_EXERCISE_ID,
            equipment_id=DEMO_EQUIPMENT_ID,
        )
        .on_conflict_do_nothing()
    )
    await session.execute(
        insert(trainer_exercise_training_types)
        .values(
            trainer_exercise_id=DEMO_TRAINER_EXERCISE_ID,
            training_type_id=DEMO_TRAINING_TYPE_ID,
        )
        .on_conflict_do_nothing()
    )
    await session.execute(
        insert(trainer_exercise_segments)
        .values(trainer_exercise_id=DEMO_TRAINER_EXERCISE_ID, segment_id=3)
        .on_conflict_do_nothing()
    )
    await insert_if_missing(
        session,
        TrainingGroup.__table__,
        {
            "id": DEMO_TRAINING_GROUP_ID,
            "trainer_id": DEMO_TRAINER_ID,
            "name": "Młodzież początkująca",
            "min_age": 7,
            "max_age": 14,
            "duration_minutes": 60,
        },
    )
    for item_id, segment_id, percentage, position in (
        (DEMO_WARMUP_SCHEMA_ITEM_ID, 1, 20, 1),
        (DEMO_MAIN_SCHEMA_ITEM_ID, 3, 70, 2),
        (DEMO_COOLDOWN_SCHEMA_ITEM_ID, 4, 10, 3),
    ):
        await insert_if_missing(
            session,
            TrainingGroupSchemaItem.__table__,
            {
                "id": item_id,
                "training_group_id": DEMO_TRAINING_GROUP_ID,
                "segment_id": segment_id,
                "percentage": percentage,
                "position": position,
            },
        )
    await insert_if_missing(
        session,
        TrainingPlan.__table__,
        {
            "id": DEMO_TRAINING_PLAN_ID,
            "trainer_id": DEMO_TRAINER_ID,
            "training_group_id": DEMO_TRAINING_GROUP_ID,
            "participant_count": 10,
            "name": "Trening demonstracyjny",
            "group_name_snapshot": "Młodzież początkująca",
            "group_min_age_snapshot": 7,
            "group_max_age_snapshot": 14,
            "training_duration_snapshot": 60,
            "available_equipment_snapshot": [
                {"id": str(DEMO_EQUIPMENT_ID), "name": "Tarcza treningowa"}
            ],
            "training_types_snapshot": [
                {"id": str(DEMO_TRAINING_TYPE_ID), "name": "Technika"}
            ],
            "schema_snapshot": [
                {
                    "position": 1,
                    "segment_id": 1,
                    "code": "WARMUP",
                    "name": "Rozgrzewka",
                    "percentage": 20,
                },
                {
                    "position": 2,
                    "segment_id": 3,
                    "code": "MAIN",
                    "name": "Część główna",
                    "percentage": 70,
                },
                {
                    "position": 3,
                    "segment_id": 4,
                    "code": "COOLDOWN",
                    "name": "Wyciszenie",
                    "percentage": 10,
                },
            ],
        },
    )
    await insert_if_missing(
        session,
        TrainingPlanExercise.__table__,
        {
            "id": DEMO_PLAN_EXERCISE_ID,
            "training_plan_id": DEMO_TRAINING_PLAN_ID,
            "trainer_exercise_id": DEMO_TRAINER_EXERCISE_ID,
            "exercise_id": DEMO_EXERCISE_ID,
            "position": 1,
            "schema_position": 2,
            "name_snapshot": "Ap chagi na tarczę",
            "description_snapshot": (
                "Kopnięcia frontalne na tarczę trzymaną przez partnera."
            ),
            "min_age_snapshot": 7,
            "max_age_snapshot": 14,
            "min_participants_snapshot": 2,
            "max_participants_snapshot": 20,
            "duration_minutes_snapshot": 10,
            "equipment_snapshot": [
                {"id": str(DEMO_EQUIPMENT_ID), "name": "Tarcza treningowa"}
            ],
            "training_types_snapshot": [
                {"id": str(DEMO_TRAINING_TYPE_ID), "name": "Technika"}
            ],
            "segments_snapshot": [{"id": 3, "code": "MAIN", "name": "Część główna"}],
        },
    )


async def seed_system_data() -> None:
    """Apply all system seed data in one transaction."""

    async with get_session_factory()() as session:
        async with session.begin():
            await seed_training_segments(session)
            await seed_demo_data(session)


async def run_seed_command() -> None:
    """Run the seed and close its database resources on the same event loop."""

    try:
        await seed_system_data()
    finally:
        await dispose_engine()


def main() -> None:
    """Run the system-data seed command."""

    asyncio.run(run_seed_command())


if __name__ == "__main__":
    main()
