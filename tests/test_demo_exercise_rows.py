"""Coverage for pure exercise seed-row generation."""

from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.db.demo_exercise_rows import (
    DemoExerciseSeedContext,
    build_demo_exercise_rows,
)
from app.db.exercise_catalog import load_exercise_catalog
from app.db.training_catalog import SYSTEM_TRAINING_SEGMENTS


def _seed_id(kind: str, key: str | int) -> UUID:
    return uuid5(NAMESPACE_URL, f"{kind}:{key}")


def _context() -> DemoExerciseSeedContext:
    """Build the same deterministic dependencies supplied by the seed command."""

    return DemoExerciseSeedContext(
        trainer_id=_seed_id("trainer", "demo"),
        seed_id=_seed_id,
        segment_ids={segment.code: segment.id for segment in SYSTEM_TRAINING_SEGMENTS},
    )


def test_builder_creates_complete_current_and_historical_exercise_rows() -> None:
    """Keep every catalogue exercise connected to its current seeded version."""

    rows = build_demo_exercise_rows(load_exercise_catalog(), _context())

    assert len(rows.exercise_rows) == 318
    assert len(rows.trainer_rows) == 318
    assert len(rows.version_rows) == len(rows.version_ids) == 326
    assert len(rows.current_versions_by_exercise) == 318
    assert set(rows.current_version_ids.values()) <= set(rows.version_ids)
    assert set(rows.current_versions_by_exercise.values()) == set(
        rows.current_version_ids.values()
    )


def test_builder_is_deterministic_and_marks_only_superseded_versions_as_archived() -> (
    None
):
    """Version history must be repeatable and preserve its current version payload."""

    exercises = load_exercise_catalog()
    context = _context()
    rows = build_demo_exercise_rows(exercises, context)
    historical = [
        row
        for row in rows.version_rows
        if row["exercise_id"] == context.seed_id("exercise", 1)
    ]

    assert rows == build_demo_exercise_rows(exercises, context)
    assert [row["version_number"] for row in historical] == [1, 2]
    assert cast(str, historical[0]["description"]).endswith(
        "Wersja archiwalna katalogu."
    )
    assert not cast(str, historical[1]["description"]).endswith(
        "Wersja archiwalna katalogu."
    )
