"""Seed the fixed catalogs and a presentation-ready demo dataset."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID, uuid5

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
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
    ExerciseScope,
    ExerciseVersionStatus,
    TrainerExerciseStatus,
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
HISTORICAL_VERSION_SOURCE_IDS = frozenset({1, 48, 96, 144, 192, 240, 288, 318})


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


@dataclass(frozen=True)
class GroupSchemaSeed:
    """One segment allocation in a demo training-group schema."""

    segment_id: int
    code: str
    name: str
    percentage: int


@dataclass(frozen=True)
class TrainingGroupSeed:
    """One group and the five historical plans shown for it."""

    key: str
    name: str
    min_age: int
    max_age: int
    duration_minutes: int
    participant_count: int
    schema: tuple[GroupSchemaSeed, ...]


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

_WARMUP = GroupSchemaSeed(1, "WARMUP", "Rozgrzewka", 20)
_GAME = GroupSchemaSeed(2, "GAME", "Zabawa", 20)
_MAIN = GroupSchemaSeed(3, "MAIN", "Ćwiczenia", 50)
_COOLDOWN = GroupSchemaSeed(4, "COOLDOWN", "Rozciąganie", 10)

DEMO_TRAINING_GROUPS = (
    TrainingGroupSeed(
        key="children",
        name="Dzieci początkujące",
        min_age=6,
        max_age=8,
        duration_minutes=45,
        participant_count=10,
        schema=(_WARMUP, _GAME, _MAIN, _COOLDOWN),
    ),
    TrainingGroupSeed(
        key="youth",
        name="Młodzicy",
        min_age=9,
        max_age=12,
        duration_minutes=60,
        participant_count=14,
        schema=(
            _WARMUP,
            GroupSchemaSeed(3, "MAIN", "Ćwiczenia", 70),
            _COOLDOWN,
        ),
    ),
    TrainingGroupSeed(
        key="teens",
        name="Młodzież zaawansowana",
        min_age=13,
        max_age=16,
        duration_minutes=75,
        participant_count=16,
        schema=(
            GroupSchemaSeed(1, "WARMUP", "Rozgrzewka", 15),
            GroupSchemaSeed(3, "MAIN", "Ćwiczenia", 75),
            _COOLDOWN,
        ),
    ),
)


def _version_id(source_id: int, version_number: int) -> UUID:
    return _seed_id("exercise-version", f"{source_id}:{version_number}")


def _current_version_number(exercise: SeedExercise) -> int:
    return 2 if exercise.source_id in HISTORICAL_VERSION_SOURCE_IDS else 1


def _exercise_version_row(
    exercise: SeedExercise,
    *,
    version_number: int,
    archived: bool,
) -> dict[str, object]:
    description = exercise.description
    if archived:
        description = f"{description}\n\nWersja archiwalna katalogu."
    return {
        "id": _version_id(exercise.source_id, version_number),
        "exercise_id": _seed_id("exercise", exercise.source_id),
        "version_number": version_number,
        "status": ExerciseVersionStatus.APPROVED,
        "name": exercise.name,
        "description": description,
        "min_age": exercise.min_age,
        "max_age": exercise.max_age,
        "min_participants": exercise.min_participants,
        "max_participants": exercise.max_participants,
        "duration_minutes": exercise.duration_minutes,
        "equipment_requirement_mode": exercise.equipment_requirement_mode,
        "physical_difficulty": exercise.physical_difficulty,
        "technical_difficulty": exercise.technical_difficulty,
        "upper_body_load": exercise.upper_body_load,
        "lower_body_load": exercise.lower_body_load,
        "core_load": exercise.core_load,
        "approved_at": datetime(2026, 10, version_number, tzinfo=UTC),
    }


async def _upsert_by_id(
    session: AsyncSession,
    table: Any,
    rows: list[dict[str, object]],
    update_columns: tuple[str, ...],
) -> None:
    if not rows:
        return
    statement = insert(table).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={column: statement.excluded[column] for column in update_columns},
        )
    )


async def _replace_associations(
    session: AsyncSession,
    table: Any,
    owner_column: str,
    owner_ids: list[UUID],
    rows: list[dict[str, object]],
) -> None:
    if owner_ids:
        await session.execute(delete(table).where(table.c[owner_column].in_(owner_ids)))
    if rows:
        await session.execute(insert(table).values(rows).on_conflict_do_nothing())


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


async def _replace_global_catalog(
    session: AsyncSession, model: Any, association_tables: tuple[Any, ...]
) -> None:
    global_catalog_ids = select(model.id).where(
        model.visibility == CatalogVisibility.GLOBAL
    )
    foreign_key = "equipment_id" if model is Equipment else "training_type_id"
    for association_table in association_tables:
        await session.execute(
            delete(association_table).where(
                association_table.c[foreign_key].in_(global_catalog_ids)
            )
        )
    await session.execute(
        delete(model).where(model.visibility == CatalogVisibility.GLOBAL)
    )


async def seed_training_types(session: AsyncSession) -> None:
    """Replace the global training-type dictionary with the source catalog."""

    await _replace_global_catalog(
        session,
        TrainingType,
        (exercise_version_training_types, trainer_exercise_training_types),
    )
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
) -> dict[str, UUID]:
    """Replace global equipment with the normalized values used by source exercises."""

    await _replace_global_catalog(
        session,
        Equipment,
        (exercise_version_equipment, trainer_exercise_equipment),
    )
    names = equipment_names(exercises)
    equipment_ids = {name: _seed_id("equipment", name) for name in names}
    await session.execute(
        insert(Equipment).values(
            [
                {
                    "id": equipment_ids[name],
                    "owner_user_id": None,
                    "name": name,
                    "visibility": CatalogVisibility.GLOBAL,
                }
                for name in names
            ]
        )
    )
    return equipment_ids


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
    equipment_ids: dict[str, UUID],
) -> dict[int, UUID]:
    """Seed global exercises, their current configurations, and version history."""

    training_type_ids = {
        training_type["name"]: training_type["id"]
        for training_type in SYSTEM_TRAINING_TYPES
    }
    segment_ids = {
        segment["code"]: segment["id"] for segment in SYSTEM_TRAINING_SEGMENTS
    }
    exercise_rows: list[dict[str, object]] = [
        {
            "id": _seed_id("exercise", exercise.source_id),
            "owner_user_id": DEMO_TRAINER_ID,
            "scope": ExerciseScope.GLOBAL,
            "name": exercise.name,
            "description": exercise.description,
            "latest_approved_version_id": None,
        }
        for exercise in exercises
    ]
    version_rows: list[dict[str, object]] = []
    current_version_ids: dict[int, UUID] = {}
    version_equipment_rows: list[dict[str, object]] = []
    version_training_type_rows: list[dict[str, object]] = []
    version_segment_rows: list[dict[str, object]] = []
    trainer_rows: list[dict[str, object]] = []
    trainer_equipment_rows: list[dict[str, object]] = []
    trainer_training_type_rows: list[dict[str, object]] = []
    trainer_segment_rows: list[dict[str, object]] = []

    for exercise in exercises:
        version_numbers = (
            (1, 2) if exercise.source_id in HISTORICAL_VERSION_SOURCE_IDS else (1,)
        )
        for version_number in version_numbers:
            version_id = _version_id(exercise.source_id, version_number)
            version_rows.append(
                _exercise_version_row(
                    exercise,
                    version_number=version_number,
                    archived=version_number == 1 and len(version_numbers) > 1,
                )
            )
            version_equipment_rows.extend(
                {
                    "exercise_version_id": version_id,
                    "equipment_id": equipment_ids[name],
                }
                for name in exercise.equipment_names
            )
            version_training_type_rows.extend(
                {
                    "exercise_version_id": version_id,
                    "training_type_id": training_type_ids[name],
                }
                for name in exercise.training_type_names
            )
            version_segment_rows.extend(
                {
                    "exercise_version_id": version_id,
                    "segment_id": segment_ids[code],
                }
                for code in exercise.segment_codes
            )

        current_version_id = _version_id(
            exercise.source_id, _current_version_number(exercise)
        )
        current_version_ids[exercise.source_id] = current_version_id
        trainer_exercise_id = _seed_id("trainer-exercise", exercise.source_id)
        trainer_rows.append(
            {
                "id": trainer_exercise_id,
                "trainer_id": DEMO_TRAINER_ID,
                "exercise_id": _seed_id("exercise", exercise.source_id),
                "source_version_id": current_version_id,
                "status": TrainerExerciseStatus.ACTIVE,
                "min_age": exercise.min_age,
                "max_age": exercise.max_age,
                "min_participants": exercise.min_participants,
                "max_participants": exercise.max_participants,
                "duration_minutes": exercise.duration_minutes,
                "equipment_requirement_mode": exercise.equipment_requirement_mode,
                "physical_difficulty": exercise.physical_difficulty,
                "technical_difficulty": exercise.technical_difficulty,
                "upper_body_load": exercise.upper_body_load,
                "lower_body_load": exercise.lower_body_load,
                "core_load": exercise.core_load,
            }
        )
        trainer_equipment_rows.extend(
            {
                "trainer_exercise_id": trainer_exercise_id,
                "equipment_id": equipment_ids[name],
            }
            for name in exercise.equipment_names
        )
        trainer_training_type_rows.extend(
            {
                "trainer_exercise_id": trainer_exercise_id,
                "training_type_id": training_type_ids[name],
            }
            for name in exercise.training_type_names
        )
        trainer_segment_rows.extend(
            {
                "trainer_exercise_id": trainer_exercise_id,
                "segment_id": segment_ids[code],
            }
            for code in exercise.segment_codes
        )

    await _upsert_by_id(
        session,
        Exercise.__table__,
        exercise_rows,
        ("owner_user_id", "scope", "name", "description"),
    )
    await _upsert_by_id(
        session,
        ExerciseVersion.__table__,
        version_rows,
        tuple(
            column
            for column in version_rows[0]
            if column not in {"id", "exercise_id", "created_at"}
        ),
    )
    await _upsert_by_id(
        session,
        TrainerExercise.__table__,
        trainer_rows,
        tuple(
            column for column in trainer_rows[0] if column not in {"id", "created_at"}
        ),
    )
    version_ids = [row["id"] for row in version_rows if isinstance(row["id"], UUID)]
    trainer_ids = [row["id"] for row in trainer_rows if isinstance(row["id"], UUID)]
    await _replace_associations(
        session,
        exercise_version_equipment,
        "exercise_version_id",
        version_ids,
        version_equipment_rows,
    )
    await _replace_associations(
        session,
        exercise_version_training_types,
        "exercise_version_id",
        version_ids,
        version_training_type_rows,
    )
    await _replace_associations(
        session,
        exercise_version_segments,
        "exercise_version_id",
        version_ids,
        version_segment_rows,
    )
    await _replace_associations(
        session,
        trainer_exercise_equipment,
        "trainer_exercise_id",
        trainer_ids,
        trainer_equipment_rows,
    )
    await _replace_associations(
        session,
        trainer_exercise_training_types,
        "trainer_exercise_id",
        trainer_ids,
        trainer_training_type_rows,
    )
    await _replace_associations(
        session,
        trainer_exercise_segments,
        "trainer_exercise_id",
        trainer_ids,
        trainer_segment_rows,
    )
    for source_id, version_id in current_version_ids.items():
        await session.execute(
            update(Exercise)
            .where(Exercise.id == _seed_id("exercise", source_id))
            .values(latest_approved_version_id=version_id)
        )
    return current_version_ids


def _plan_exercise(
    exercises: tuple[SeedExercise, ...],
    group: TrainingGroupSeed,
    schema_item: GroupSchemaSeed,
    selection_offset: int,
) -> SeedExercise:
    eligible = [
        exercise
        for exercise in exercises
        if schema_item.code in exercise.segment_codes
        and exercise.max_age >= group.min_age
        and exercise.min_age <= group.max_age
    ]
    segment_minutes = group.duration_minutes * schema_item.percentage // 100
    within_duration = [
        exercise
        for exercise in eligible
        if exercise.duration_minutes <= max(segment_minutes, 1)
    ]
    candidates = within_duration or eligible
    if not candidates:
        raise ValueError(f"No {schema_item.code} exercise for {group.name}")
    return candidates[selection_offset % len(candidates)]


def _segment_snapshot(segment_code: str) -> dict[str, object]:
    return next(
        {
            "id": segment["id"],
            "code": segment["code"],
            "name": segment["name"],
        }
        for segment in SYSTEM_TRAINING_SEGMENTS
        if segment["code"] == segment_code
    )


async def seed_training_groups_and_plans(
    session: AsyncSession,
    exercises: tuple[SeedExercise, ...],
    equipment_ids: dict[str, UUID],
    current_version_ids: dict[int, UUID],
) -> None:
    """Create three groups with five historical plans each."""

    training_type_ids = {
        training_type["name"]: training_type["id"]
        for training_type in SYSTEM_TRAINING_TYPES
    }
    group_ids = {
        group.key: _seed_id("training-group", group.key)
        for group in DEMO_TRAINING_GROUPS
    }
    group_rows = [
        {
            "id": group_ids[group.key],
            "trainer_id": DEMO_TRAINER_ID,
            "name": group.name,
            "min_age": group.min_age,
            "max_age": group.max_age,
            "duration_minutes": group.duration_minutes,
        }
        for group in DEMO_TRAINING_GROUPS
    ]
    await _upsert_by_id(
        session,
        TrainingGroup.__table__,
        group_rows,
        ("trainer_id", "name", "min_age", "max_age", "duration_minutes"),
    )

    group_schema_rows: list[dict[str, object]] = []
    plan_rows: list[dict[str, object]] = []
    plan_exercise_rows: list[dict[str, object]] = []
    plan_ids: list[UUID] = []
    for group_index, group in enumerate(DEMO_TRAINING_GROUPS):
        group_id = group_ids[group.key]
        for position, schema_item in enumerate(group.schema, start=1):
            group_schema_rows.append(
                {
                    "id": _seed_id("group-schema", f"{group.key}:{position}"),
                    "training_group_id": group_id,
                    "segment_id": schema_item.segment_id,
                    "percentage": schema_item.percentage,
                    "position": position,
                }
            )
        for plan_number in range(1, 6):
            plan_id = _seed_id("training-plan", f"{group.key}:{plan_number}")
            plan_ids.append(plan_id)
            selected = [
                _plan_exercise(
                    exercises,
                    group,
                    schema_item,
                    group_index * 47 + plan_number * 11 + position * 7,
                )
                for position, schema_item in enumerate(group.schema, start=1)
            ]
            used_equipment = tuple(
                sorted(
                    {name for exercise in selected for name in exercise.equipment_names}
                )
            )
            used_training_types = tuple(
                sorted(
                    {
                        name
                        for exercise in selected
                        for name in exercise.training_type_names
                    }
                )
            )
            plan_rows.append(
                {
                    "id": plan_id,
                    "trainer_id": DEMO_TRAINER_ID,
                    "training_group_id": group_id,
                    "participant_count": group.participant_count + plan_number - 1,
                    "name": f"{group.name} – trening {plan_number}",
                    "group_name_snapshot": group.name,
                    "group_min_age_snapshot": group.min_age,
                    "group_max_age_snapshot": group.max_age,
                    "training_duration_snapshot": group.duration_minutes,
                    "available_equipment_snapshot": [
                        {"id": str(equipment_ids[name]), "name": name}
                        for name in used_equipment
                    ],
                    "training_types_snapshot": [
                        {"id": str(training_type_ids[name]), "name": name}
                        for name in used_training_types
                    ],
                    "schema_snapshot": [
                        {
                            "position": position,
                            "segment_id": schema_item.segment_id,
                            "code": schema_item.code,
                            "name": schema_item.name,
                            "percentage": schema_item.percentage,
                        }
                        for position, schema_item in enumerate(group.schema, start=1)
                    ],
                }
            )
            for position, (_schema_item, exercise) in enumerate(
                zip(group.schema, selected, strict=True), start=1
            ):
                plan_exercise_rows.append(
                    {
                        "id": _seed_id(
                            "training-plan-exercise",
                            f"{group.key}:{plan_number}:{position}",
                        ),
                        "training_plan_id": plan_id,
                        "trainer_exercise_id": _seed_id(
                            "trainer-exercise", exercise.source_id
                        ),
                        "exercise_id": _seed_id("exercise", exercise.source_id),
                        "exercise_version_id": current_version_ids[exercise.source_id],
                        "position": position,
                        "schema_position": position,
                        "name_snapshot": exercise.name,
                        "description_snapshot": exercise.description,
                        "min_age_snapshot": exercise.min_age,
                        "max_age_snapshot": exercise.max_age,
                        "min_participants_snapshot": exercise.min_participants,
                        "max_participants_snapshot": exercise.max_participants,
                        "duration_minutes_snapshot": exercise.duration_minutes,
                        "equipment_snapshot": [
                            {"id": str(equipment_ids[name]), "name": name}
                            for name in exercise.equipment_names
                        ],
                        "training_types_snapshot": [
                            {"id": str(training_type_ids[name]), "name": name}
                            for name in exercise.training_type_names
                        ],
                        "segments_snapshot": [
                            _segment_snapshot(segment_code)
                            for segment_code in exercise.segment_codes
                        ],
                    }
                )
    await _replace_associations(
        session,
        TrainingGroupSchemaItem.__table__,
        "training_group_id",
        list(group_ids.values()),
        group_schema_rows,
    )
    await session.execute(
        delete(TrainingPlanExercise).where(
            TrainingPlanExercise.training_plan_id.in_(plan_ids)
        )
    )
    await _upsert_by_id(
        session,
        TrainingPlan.__table__,
        plan_rows,
        tuple(
            column for column in plan_rows[0] if column not in {"id", "generated_at"}
        ),
    )
    await session.execute(insert(TrainingPlanExercise).values(plan_exercise_rows))


async def seed_demo_data(session: AsyncSession) -> None:
    """Insert the demo trainer, global catalog exercises, groups, and plans."""

    exercises = load_exercise_catalog()
    logger.info("Seeding %d source exercises", len(exercises))
    for user in DEMO_LOCAL_USERS:
        await upsert_local_user(session, user)
    await _remove_previous_demo_data(session)
    equipment_ids = await seed_equipment(session, exercises)
    current_version_ids = await seed_exercises(session, exercises, equipment_ids)
    await seed_training_groups_and_plans(
        session, exercises, equipment_ids, current_version_ids
    )


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
