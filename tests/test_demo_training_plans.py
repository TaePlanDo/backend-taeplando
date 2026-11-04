"""Coverage for the deterministic presentation training-plan builder."""

from collections import Counter
from typing import TypedDict, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.db.demo_training_plans import DemoTrainingContext, build_demo_training_rows
from app.db.exercise_catalog import load_exercise_catalog
from app.db.training_catalog import SYSTEM_TRAINING_SEGMENTS


class _SchemaSnapshot(TypedDict):
    position: int
    segment_id: int
    code: str
    name: str
    percentage: int


def _seed_id(kind: str, key: str | int) -> UUID:
    return uuid5(NAMESPACE_URL, f"{kind}:{key}")


def _context() -> DemoTrainingContext:
    """Build stable catalog lookups without relying on database state."""

    exercises = load_exercise_catalog()
    return DemoTrainingContext(
        trainer_id=_seed_id("trainer", "demo"),
        seed_id=_seed_id,
        segment_snapshots={
            segment.code: {
                "id": segment.id,
                "code": segment.code,
                "name": segment.name,
            }
            for segment in SYSTEM_TRAINING_SEGMENTS
        },
        current_version_ids={
            exercise.source_id: _seed_id("version", exercise.source_id)
            for exercise in exercises
        },
    )


def test_builder_creates_three_coherent_groups_with_five_plans_each() -> None:
    """Keep the demo presentation data complete and structurally consistent."""

    rows = build_demo_training_rows(load_exercise_catalog(), _context())

    assert len(rows.group_rows) == 3
    assert [row["name"] for row in rows.group_rows] == [
        "Żarów gr. 1",
        "Jaworzyna gr. 1",
        "Jaworzyna gr. 2",
    ]
    assert len(rows.group_schema_rows) == 10
    assert len(rows.plan_rows) == 15
    assert len(rows.plan_exercise_rows) == 50
    assert set(
        Counter(row["training_group_id"] for row in rows.plan_rows).values()
    ) == {5}
    assert {row["training_group_id"] for row in rows.group_schema_rows} == set(
        rows.group_ids.values()
    )
    assert rows.group_schema_rows[:4] == [
        {
            "id": _seed_id("group-schema", f"children:{position}"),
            "training_group_id": rows.group_ids["children"],
            "segment_id": segment_id,
            "percentage": percentage,
            "position": position,
        }
        for position, segment_id, percentage in (
            (1, 1, 20),
            (2, 2, 20),
            (3, 3, 50),
            (4, 4, 10),
        )
    ]
    assert all(
        sum(
            item["percentage"]
            for item in cast(list[_SchemaSnapshot], plan["schema_snapshot"])
        )
        == 100
        for plan in rows.plan_rows
    )


def test_builder_is_deterministic_and_uses_current_exercise_versions() -> None:
    """Plans must be repeatable and reference the catalog's current versions."""

    exercises = load_exercise_catalog()
    context = _context()

    rows = build_demo_training_rows(exercises, context)

    assert rows == build_demo_training_rows(exercises, context)
    assert {row["exercise_version_id"] for row in rows.plan_exercise_rows} <= set(
        context.current_version_ids.values()
    )
