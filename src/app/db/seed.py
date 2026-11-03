"""Seed the fixed catalogs and a presentation-ready demo dataset."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import TypedDict, cast
from uuid import UUID, uuid5

from sqlalchemy import Table, case, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import FromClause

from app.core.security import hash_password
from app.db.demo_exercise_rows import (
    DemoExerciseSeedContext,
    build_demo_exercise_rows,
)
from app.db.demo_training_plans import (
    DemoTrainingContext,
    SegmentSnapshot,
    build_demo_training_rows,
)
from app.db.exercise_catalog import SeedExercise, equipment_names, load_exercise_catalog
from app.db.session import dispose_engine, get_session_factory
from app.models.associations import (
    exercise_version_equipment,
    exercise_version_segments,
    exercise_version_training_types,
    trainer_exercise_equipment,
    trainer_exercise_segments,
    trainer_exercise_training_types,
)
from app.models.catalogs import Equipment, TrainingSegment, TrainingType
from app.models.enums import (
    AuthMethod,
    CatalogVisibility,
)
from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise
from app.models.training import (
    TrainingGroup,
    TrainingGroupSchemaItem,
    TrainingPlan,
    TrainingPlanExercise,
)
from app.models.users import User

logger = logging.getLogger(__name__)

SEED_NAMESPACE = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a00")
DEMO_TRAINER_ID = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a01")
DEMO_TRAINER_EMAIL = "demo.trener@gmail.com"
DEMO_TRAINER_PASSWORD = "Demo123!"


class TrainingSegmentSeed(TypedDict):
    """One immutable entry of the system training-segment dictionary."""

    id: int
    code: str
    name: str


class TrainingTypeSeed(TypedDict):
    """One immutable entry of the system training-type catalog."""

    id: UUID
    name: str


class LocalUserSeed(TypedDict):
    """One local user created by the development seed."""

    id: UUID
    email: str
    full_name: str
    password: str


SYSTEM_TRAINING_SEGMENTS: Sequence[TrainingSegmentSeed] = (
    {"id": 1, "code": "WARMUP", "name": "Rozgrzewka"},
    {"id": 2, "code": "GAME", "name": "Zabawa"},
    {"id": 3, "code": "MAIN", "name": "Ćwiczenia"},
    {"id": 4, "code": "COOLDOWN", "name": "Rozciąganie"},
)

SYSTEM_TRAINING_TYPE_NAMES = (
    "Celność",
    "Core",
    "Dystans",
    "Kondycja",
    "Koordynacja",
    "Mobilność",
    "Mobilność – Dynamiczne",
    "Mobilność – Statyczne",
    "Moc",
    "Obrona",
    "Ogólnorozwojowy",
    "Pamięć",
    "Reakcja",
    "Równowaga",
    "Siła",
    "Siła grzbietu",
    "Stabilizacja",
    "Szybkość",
    "Taktyka",
    "Technika",
    "Układy formalne",
    "Walka",
    "Wytrzymałość",
    "Zabawa",
)


def _seed_id(kind: str, key: str | int) -> UUID:
    return uuid5(SEED_NAMESPACE, f"{kind}:{key}")


SYSTEM_TRAINING_TYPES: Sequence[TrainingTypeSeed] = tuple(
    {"id": _seed_id("training-type", name), "name": name}
    for name in SYSTEM_TRAINING_TYPE_NAMES
)

DEMO_LOCAL_USERS: Sequence[LocalUserSeed] = (
    {
        "id": DEMO_TRAINER_ID,
        "email": DEMO_TRAINER_EMAIL,
        "full_name": "Trener demonstracyjny",
        "password": DEMO_TRAINER_PASSWORD,
    },
)


async def _upsert_by_id(
    session: AsyncSession,
    table: FromClause,
    rows: list[dict[str, object]],
    update_columns: tuple[str, ...],
) -> None:
    if not rows:
        return
    writable_table = cast(Table, table)
    statement = insert(writable_table).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={column: statement.excluded[column] for column in update_columns},
        )
    )


async def _replace_associations(
    session: AsyncSession,
    table: FromClause,
    owner_column: str,
    owner_ids: list[UUID],
    rows: list[dict[str, object]],
) -> None:
    writable_table = cast(Table, table)
    if owner_ids:
        await session.execute(
            delete(writable_table).where(writable_table.c[owner_column].in_(owner_ids))
        )
    if rows:
        await session.execute(
            insert(writable_table).values(rows).on_conflict_do_nothing()
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


async def _clear_global_training_types(session: AsyncSession) -> None:
    global_training_type_ids = select(TrainingType.id).where(
        TrainingType.visibility == CatalogVisibility.GLOBAL
    )
    for association_table in (
        exercise_version_training_types,
        trainer_exercise_training_types,
    ):
        await session.execute(
            delete(association_table).where(
                association_table.c.training_type_id.in_(global_training_type_ids)
            )
        )
    await session.execute(
        delete(TrainingType).where(TrainingType.visibility == CatalogVisibility.GLOBAL)
    )


async def _clear_global_equipment(session: AsyncSession) -> None:
    global_equipment_ids = select(Equipment.id).where(
        Equipment.visibility == CatalogVisibility.GLOBAL
    )
    for association_table in (exercise_version_equipment, trainer_exercise_equipment):
        await session.execute(
            delete(association_table).where(
                association_table.c.equipment_id.in_(global_equipment_ids)
            )
        )
    await session.execute(
        delete(Equipment).where(Equipment.visibility == CatalogVisibility.GLOBAL)
    )


async def seed_training_types(session: AsyncSession) -> None:
    """Replace the global training-type dictionary with the source catalog."""

    await _clear_global_training_types(session)
    await session.execute(
        insert(TrainingType).values(
            [
                {
                    **training_type,
                    "owner_user_id": None,
                    "visibility": CatalogVisibility.GLOBAL,
                }
                for training_type in SYSTEM_TRAINING_TYPES
            ]
        )
    )


async def seed_equipment(
    session: AsyncSession, exercises: tuple[SeedExercise, ...]
) -> None:
    """Replace global equipment with the normalized values used by source exercises."""

    await _clear_global_equipment(session)
    names = equipment_names(exercises)
    await session.execute(
        insert(Equipment).values(
            [
                {
                    "id": _seed_id("equipment", name),
                    "owner_user_id": None,
                    "name": name,
                    "visibility": CatalogVisibility.GLOBAL,
                }
                for name in names
            ]
        )
    )


async def upsert_local_user(session: AsyncSession, user: LocalUserSeed) -> None:
    """Create or update a deterministic local user with a fresh bcrypt hash."""

    statement = insert(User).values(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        auth_method=AuthMethod.LOCAL,
        password_hash=hash_password(user["password"]),
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "email": statement.excluded.email,
                "full_name": statement.excluded.full_name,
                "auth_method": statement.excluded.auth_method,
                "password_hash": statement.excluded.password_hash,
                "oauth_subject": None,
            },
        )
    )


async def _remove_previous_demo_data(session: AsyncSession) -> None:
    """Remove the single-record demo dataset used before the catalog seed."""

    old_ids = {
        "equipment": UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a02"),
        "training_type": UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a03"),
        "exercise": UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a04"),
        "trainer_exercise": UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a05"),
        "training_group": UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a06"),
        "training_plan": UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a10"),
        "plan_exercise": UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a11"),
    }
    await session.execute(
        delete(TrainingPlanExercise).where(
            TrainingPlanExercise.id == old_ids["plan_exercise"]
        )
    )
    await session.execute(
        delete(TrainingPlan).where(TrainingPlan.id == old_ids["training_plan"])
    )
    await session.execute(
        delete(TrainingGroupSchemaItem).where(
            TrainingGroupSchemaItem.training_group_id == old_ids["training_group"]
        )
    )
    await session.execute(
        delete(TrainingGroup).where(TrainingGroup.id == old_ids["training_group"])
    )
    for association_table in (
        trainer_exercise_equipment,
        trainer_exercise_training_types,
        trainer_exercise_segments,
    ):
        await session.execute(
            delete(association_table).where(
                association_table.c.trainer_exercise_id == old_ids["trainer_exercise"]
            )
        )
    await session.execute(
        delete(TrainerExercise).where(TrainerExercise.id == old_ids["trainer_exercise"])
    )
    await session.execute(delete(Exercise).where(Exercise.id == old_ids["exercise"]))
    await session.execute(delete(Equipment).where(Equipment.id == old_ids["equipment"]))
    await session.execute(
        delete(TrainingType).where(TrainingType.id == old_ids["training_type"])
    )


async def seed_exercises(
    session: AsyncSession,
    exercises: tuple[SeedExercise, ...],
) -> dict[int, UUID]:
    """Seed global exercises, their current configurations, and version history."""

    context = DemoExerciseSeedContext(
        trainer_id=DEMO_TRAINER_ID,
        seed_id=_seed_id,
        segment_ids={
            segment["code"]: segment["id"] for segment in SYSTEM_TRAINING_SEGMENTS
        },
    )
    rows = build_demo_exercise_rows(exercises, context)

    await _upsert_by_id(
        session,
        Exercise.__table__,
        rows.exercise_rows,
        ("owner_user_id", "scope", "name", "description"),
    )
    await _upsert_by_id(
        session,
        ExerciseVersion.__table__,
        rows.version_rows,
        tuple(
            column
            for column in rows.version_rows[0]
            if column not in {"id", "exercise_id", "created_at"}
        ),
    )
    await _upsert_by_id(
        session,
        TrainerExercise.__table__,
        rows.trainer_rows,
        tuple(
            column
            for column in rows.trainer_rows[0]
            if column not in {"id", "created_at"}
        ),
    )
    await _replace_associations(
        session,
        exercise_version_equipment,
        "exercise_version_id",
        rows.version_ids,
        rows.version_equipment_rows,
    )
    await _replace_associations(
        session,
        exercise_version_training_types,
        "exercise_version_id",
        rows.version_ids,
        rows.version_training_type_rows,
    )
    await _replace_associations(
        session,
        exercise_version_segments,
        "exercise_version_id",
        rows.version_ids,
        rows.version_segment_rows,
    )
    await _replace_associations(
        session,
        trainer_exercise_equipment,
        "trainer_exercise_id",
        rows.trainer_ids,
        rows.trainer_equipment_rows,
    )
    await _replace_associations(
        session,
        trainer_exercise_training_types,
        "trainer_exercise_id",
        rows.trainer_ids,
        rows.trainer_training_type_rows,
    )
    await _replace_associations(
        session,
        trainer_exercise_segments,
        "trainer_exercise_id",
        rows.trainer_ids,
        rows.trainer_segment_rows,
    )
    await session.execute(
        update(Exercise)
        .where(Exercise.id.in_(rows.current_versions_by_exercise))
        .values(
            latest_approved_version_id=case(
                rows.current_versions_by_exercise,
                value=Exercise.id,
            )
        )
    )
    return rows.current_version_ids


async def seed_training_groups_and_plans(
    session: AsyncSession,
    exercises: tuple[SeedExercise, ...],
    current_version_ids: dict[int, UUID],
) -> None:
    """Persist the deterministic presentation groups and their plan snapshots."""

    segment_snapshots: dict[str, SegmentSnapshot] = {
        segment["code"]: {
            "id": segment["id"],
            "code": segment["code"],
            "name": segment["name"],
        }
        for segment in SYSTEM_TRAINING_SEGMENTS
    }
    context = DemoTrainingContext(
        trainer_id=DEMO_TRAINER_ID,
        seed_id=_seed_id,
        segment_snapshots=segment_snapshots,
        current_version_ids=current_version_ids,
    )
    rows = build_demo_training_rows(exercises, context)
    await _upsert_by_id(
        session,
        TrainingGroup.__table__,
        rows.group_rows,
        ("trainer_id", "name", "min_age", "max_age", "duration_minutes"),
    )
    await _replace_associations(
        session,
        TrainingGroupSchemaItem.__table__,
        "training_group_id",
        list(rows.group_ids.values()),
        rows.group_schema_rows,
    )
    await session.execute(
        delete(TrainingPlanExercise).where(
            TrainingPlanExercise.training_plan_id.in_(rows.plan_ids)
        )
    )
    await _upsert_by_id(
        session,
        TrainingPlan.__table__,
        rows.plan_rows,
        tuple(
            column
            for column in rows.plan_rows[0]
            if column not in {"id", "generated_at"}
        ),
    )
    await session.execute(insert(TrainingPlanExercise).values(rows.plan_exercise_rows))


async def seed_demo_data(session: AsyncSession) -> None:
    """Insert the demo trainer, global catalog exercises, groups, and plans."""

    exercises = load_exercise_catalog()
    logger.info("Seeding %d source exercises", len(exercises))
    for user in DEMO_LOCAL_USERS:
        await upsert_local_user(session, user)
    await _remove_previous_demo_data(session)
    await seed_equipment(session, exercises)
    current_version_ids = await seed_exercises(session, exercises)
    await seed_training_groups_and_plans(session, exercises, current_version_ids)


async def seed_system_data() -> None:
    """Apply all system seed data in one transaction."""

    logger.info("Starting system-data seed transaction")
    async with get_session_factory()() as session:
        async with session.begin():
            await seed_training_segments(session)
            await seed_training_types(session)
            await seed_demo_data(session)
    logger.info("System-data seed transaction completed")


async def run_seed_command() -> None:
    """Run the seed and close its database resources on the same event loop."""

    try:
        await seed_system_data()
    except Exception:
        logger.exception("System-data seed failed")
        raise
    finally:
        await dispose_engine()


def main() -> None:
    """Run the seed and configure command-line logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_seed_command())


if __name__ == "__main__":
    main()
