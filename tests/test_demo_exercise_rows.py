"""Coverage for pure exercise seed-row generation."""

from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.db.demo_exercise_rows import (
    DemoExerciseSeedContext,
    build_demo_exercise_rows,
)
from app.db.exercise_catalog import load_exercise_catalog
from app.db.training_catalog import SYSTEM_TRAINING_SEGMENTS
from app.media.manifest import MEDIA_URL_FILES


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
    assert all(
        field not in row
        for row in (*rows.exercise_rows, *rows.version_rows)
        for field in MEDIA_URL_FILES
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


def test_builder_adds_media_to_exercises_and_all_seeded_versions() -> None:
    """Optional media must cover both current rows and historical seed versions."""

    media = {
        "image_url": "https://cdn.example.com/exercises/1/thumb-dark.webp",
        "animation_url": "https://cdn.example.com/exercises/1/anim-dark.webp",
        "image_url_light": "https://cdn.example.com/exercises/1/thumb-light.webp",
        "animation_url_light": "https://cdn.example.com/exercises/1/anim-light.webp",
    }
    context = _context()
    context = DemoExerciseSeedContext(
        trainer_id=context.trainer_id,
        seed_id=context.seed_id,
        segment_ids=context.segment_ids,
        media_urls={1: media},
    )

    rows = build_demo_exercise_rows(load_exercise_catalog(), context)
    exercise_id = context.seed_id("exercise", 1)
    exercise_row = next(row for row in rows.exercise_rows if row["id"] == exercise_id)
    version_rows = [
        row for row in rows.version_rows if row["exercise_id"] == exercise_id
    ]

    assert {field: exercise_row[field] for field in media} == media
    assert len(version_rows) == 2
    assert all({field: row[field] for field in media} == media for row in version_rows)
