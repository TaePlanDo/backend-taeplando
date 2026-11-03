"""Pure builders for the presentation training groups and their plan snapshots."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from app.db.exercise_catalog import SeedExercise


@dataclass(frozen=True)
class GroupSchemaSeed:
    """One segment allocation in a demo training-group schema."""

    code: str
    percentage: int


class SegmentSnapshot(TypedDict):
    """The system segment fields stored with an immutable training plan."""

    id: int
    code: str
    name: str


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


@dataclass(frozen=True)
class DemoTrainingRows:
    """All rows required for the groups, plans, and plan exercises."""

    group_ids: dict[str, UUID]
    group_rows: list[dict[str, object]]
    group_schema_rows: list[dict[str, object]]
    plan_ids: list[UUID]
    plan_rows: list[dict[str, object]]
    plan_exercise_rows: list[dict[str, object]]


@dataclass(frozen=True)
class DemoTrainingContext:
    """Stable seed dependencies used to build presentation training plans."""

    trainer_id: UUID
    seed_id: Callable[[str, str | int], UUID]
    equipment_ids: Mapping[str, UUID]
    training_type_ids: Mapping[str, UUID]
    segment_snapshots: Mapping[str, SegmentSnapshot]
    current_version_ids: Mapping[int, UUID]


_WARMUP = GroupSchemaSeed("WARMUP", 20)
_GAME = GroupSchemaSeed("GAME", 20)
_MAIN = GroupSchemaSeed("MAIN", 50)
_COOLDOWN = GroupSchemaSeed("COOLDOWN", 10)

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
            GroupSchemaSeed("MAIN", 70),
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
            GroupSchemaSeed("WARMUP", 15),
            GroupSchemaSeed("MAIN", 75),
            _COOLDOWN,
        ),
    ),
)
PLANS_PER_GROUP = 5


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


def _schema_snapshot(
    position: int,
    schema_item: GroupSchemaSeed,
    segment: SegmentSnapshot,
) -> dict[str, object]:
    """Build one persisted schema snapshot from the canonical segment catalog."""

    return {
        "position": position,
        "segment_id": segment["id"],
        "code": segment["code"],
        "name": segment["name"],
        "percentage": schema_item.percentage,
    }


def build_demo_training_rows(
    exercises: tuple[SeedExercise, ...],
    context: DemoTrainingContext,
) -> DemoTrainingRows:
    """Build deterministic rows for three groups and five plans per group."""

    group_ids = {
        group.key: context.seed_id("training-group", group.key)
        for group in DEMO_TRAINING_GROUPS
    }
    group_rows = [
        {
            "id": group_ids[group.key],
            "trainer_id": context.trainer_id,
            "name": group.name,
            "min_age": group.min_age,
            "max_age": group.max_age,
            "duration_minutes": group.duration_minutes,
        }
        for group in DEMO_TRAINING_GROUPS
    ]
    group_schema_rows: list[dict[str, object]] = []
    plan_rows: list[dict[str, object]] = []
    plan_exercise_rows: list[dict[str, object]] = []
    plan_ids: list[UUID] = []

    for group_index, group in enumerate(DEMO_TRAINING_GROUPS):
        group_id = group_ids[group.key]
        for position, schema_item in enumerate(group.schema, start=1):
            segment = context.segment_snapshots[schema_item.code]
            group_schema_rows.append(
                {
                    "id": context.seed_id("group-schema", f"{group.key}:{position}"),
                    "training_group_id": group_id,
                    "segment_id": segment["id"],
                    "percentage": schema_item.percentage,
                    "position": position,
                }
            )
        for plan_index in range(PLANS_PER_GROUP):
            plan_number = plan_index + 1
            plan_id = context.seed_id("training-plan", f"{group.key}:{plan_number}")
            plan_ids.append(plan_id)
            selected = [
                _plan_exercise(
                    exercises,
                    group,
                    schema_item,
                    (group_index * PLANS_PER_GROUP + plan_index) * len(group.schema)
                    + schema_index,
                )
                for schema_index, schema_item in enumerate(group.schema)
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
                    "trainer_id": context.trainer_id,
                    "training_group_id": group_id,
                    "participant_count": group.participant_count + plan_number - 1,
                    "name": f"{group.name} – trening {plan_number}",
                    "group_name_snapshot": group.name,
                    "group_min_age_snapshot": group.min_age,
                    "group_max_age_snapshot": group.max_age,
                    "training_duration_snapshot": group.duration_minutes,
                    "available_equipment_snapshot": [
                        {"id": str(context.equipment_ids[name]), "name": name}
                        for name in used_equipment
                    ],
                    "training_types_snapshot": [
                        {"id": str(context.training_type_ids[name]), "name": name}
                        for name in used_training_types
                    ],
                    "schema_snapshot": [
                        _schema_snapshot(
                            position,
                            schema_item,
                            context.segment_snapshots[schema_item.code],
                        )
                        for position, schema_item in enumerate(group.schema, start=1)
                    ],
                }
            )
            for position, exercise in enumerate(selected, start=1):
                plan_exercise_rows.append(
                    {
                        "id": context.seed_id(
                            "training-plan-exercise",
                            f"{group.key}:{plan_number}:{position}",
                        ),
                        "training_plan_id": plan_id,
                        "trainer_exercise_id": context.seed_id(
                            "trainer-exercise", exercise.source_id
                        ),
                        "exercise_id": context.seed_id("exercise", exercise.source_id),
                        "exercise_version_id": context.current_version_ids[
                            exercise.source_id
                        ],
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
                            {"id": str(context.equipment_ids[name]), "name": name}
                            for name in exercise.equipment_names
                        ],
                        "training_types_snapshot": [
                            {"id": str(context.training_type_ids[name]), "name": name}
                            for name in exercise.training_type_names
                        ],
                        "segments_snapshot": [
                            context.segment_snapshots[segment_code]
                            for segment_code in exercise.segment_codes
                        ],
                    }
                )
    return DemoTrainingRows(
        group_ids=group_ids,
        group_rows=group_rows,
        group_schema_rows=group_schema_rows,
        plan_ids=plan_ids,
        plan_rows=plan_rows,
        plan_exercise_rows=plan_exercise_rows,
    )
