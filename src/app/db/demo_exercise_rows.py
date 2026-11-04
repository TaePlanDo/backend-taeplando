"""Pure builders for the global exercise catalogue and trainer configurations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.db.exercise_catalog import SeedExercise
from app.models.enums import (
    ExerciseScope,
    ExerciseVersionStatus,
    TrainerExerciseStatus,
)

VERSIONED_EXERCISE_SOURCE_IDS = frozenset({1, 48, 96, 144, 192, 240, 288, 318})


@dataclass(frozen=True)
class DemoExerciseSeedContext:
    """Stable dependencies needed to build deterministic exercise seed rows."""

    trainer_id: UUID
    seed_id: Callable[[str, str | int], UUID]
    segment_ids: Mapping[str, int]


@dataclass(frozen=True)
class DemoExerciseRows:
    """All relational rows derived from the checked-in exercise catalogue."""

    exercise_rows: list[dict[str, object]]
    version_rows: list[dict[str, object]]
    version_equipment_rows: list[dict[str, object]]
    version_training_type_rows: list[dict[str, object]]
    version_segment_rows: list[dict[str, object]]
    trainer_rows: list[dict[str, object]]
    trainer_equipment_rows: list[dict[str, object]]
    trainer_training_type_rows: list[dict[str, object]]
    trainer_segment_rows: list[dict[str, object]]
    version_ids: list[UUID]
    trainer_ids: list[UUID]
    current_versions_by_exercise: dict[UUID, UUID]
    current_version_ids: dict[int, UUID]


def _version_numbers(exercise: SeedExercise) -> tuple[int, ...]:
    """Return every version seeded for one source exercise in chronological order."""

    if exercise.source_id in VERSIONED_EXERCISE_SOURCE_IDS:
        return (1, 2)
    return (1,)


def _planning_attributes(exercise: SeedExercise) -> dict[str, object]:
    """Map fields shared by global versions and trainer configurations."""

    return {
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


def _version_id(
    context: DemoExerciseSeedContext,
    source_id: int,
    version_number: int,
) -> UUID:
    return context.seed_id("exercise-version", f"{source_id}:{version_number}")


def _exercise_version_row(
    context: DemoExerciseSeedContext,
    exercise: SeedExercise,
    *,
    version_number: int,
    archived: bool,
) -> dict[str, object]:
    description = exercise.description
    if archived:
        description = f"{description}\n\nWersja archiwalna katalogu."
    return {
        "id": _version_id(context, exercise.source_id, version_number),
        "exercise_id": context.seed_id("exercise", exercise.source_id),
        "version_number": version_number,
        "status": ExerciseVersionStatus.APPROVED,
        "name": exercise.name,
        "description": description,
        **_planning_attributes(exercise),
        "approved_at": datetime(2026, 10, version_number, tzinfo=UTC),
    }


def build_demo_exercise_rows(
    exercises: tuple[SeedExercise, ...],
    context: DemoExerciseSeedContext,
) -> DemoExerciseRows:
    """Build global versions, trainer configurations, and all their relations."""

    exercise_rows: list[dict[str, object]] = [
        {
            "id": context.seed_id("exercise", exercise.source_id),
            "owner_user_id": context.trainer_id,
            "scope": ExerciseScope.GLOBAL,
            "name": exercise.name,
            "description": exercise.description,
            "latest_approved_version_id": None,
        }
        for exercise in exercises
    ]
    version_rows: list[dict[str, object]] = []
    version_equipment_rows: list[dict[str, object]] = []
    version_training_type_rows: list[dict[str, object]] = []
    version_segment_rows: list[dict[str, object]] = []
    trainer_rows: list[dict[str, object]] = []
    trainer_equipment_rows: list[dict[str, object]] = []
    trainer_training_type_rows: list[dict[str, object]] = []
    trainer_segment_rows: list[dict[str, object]] = []
    version_ids: list[UUID] = []
    trainer_ids: list[UUID] = []
    current_versions_by_exercise: dict[UUID, UUID] = {}
    current_version_ids: dict[int, UUID] = {}

    for exercise in exercises:
        version_numbers = _version_numbers(exercise)
        for version_number in version_numbers:
            version_id = _version_id(context, exercise.source_id, version_number)
            version_ids.append(version_id)
            version_rows.append(
                _exercise_version_row(
                    context,
                    exercise,
                    version_number=version_number,
                    archived=version_number != version_numbers[-1],
                )
            )
            version_equipment_rows.extend(
                {
                    "exercise_version_id": version_id,
                    "equipment_id": context.seed_id("equipment", name),
                }
                for name in exercise.equipment_names
            )
            version_training_type_rows.extend(
                {
                    "exercise_version_id": version_id,
                    "training_type_id": context.seed_id("training-type", name),
                }
                for name in exercise.training_type_names
            )
            version_segment_rows.extend(
                {
                    "exercise_version_id": version_id,
                    "segment_id": context.segment_ids[code],
                }
                for code in exercise.segment_codes
            )

        current_version_id = _version_id(
            context, exercise.source_id, version_numbers[-1]
        )
        exercise_id = context.seed_id("exercise", exercise.source_id)
        current_version_ids[exercise.source_id] = current_version_id
        current_versions_by_exercise[exercise_id] = current_version_id
        trainer_exercise_id = context.seed_id("trainer-exercise", exercise.source_id)
        trainer_ids.append(trainer_exercise_id)
        trainer_rows.append(
            {
                "id": trainer_exercise_id,
                "trainer_id": context.trainer_id,
                "exercise_id": exercise_id,
                "source_version_id": current_version_id,
                "status": TrainerExerciseStatus.ACTIVE,
                **_planning_attributes(exercise),
            }
        )
        trainer_equipment_rows.extend(
            {
                "trainer_exercise_id": trainer_exercise_id,
                "equipment_id": context.seed_id("equipment", name),
            }
            for name in exercise.equipment_names
        )
        trainer_training_type_rows.extend(
            {
                "trainer_exercise_id": trainer_exercise_id,
                "training_type_id": context.seed_id("training-type", name),
            }
            for name in exercise.training_type_names
        )
        trainer_segment_rows.extend(
            {
                "trainer_exercise_id": trainer_exercise_id,
                "segment_id": context.segment_ids[code],
            }
            for code in exercise.segment_codes
        )

    return DemoExerciseRows(
        exercise_rows=exercise_rows,
        version_rows=version_rows,
        version_equipment_rows=version_equipment_rows,
        version_training_type_rows=version_training_type_rows,
        version_segment_rows=version_segment_rows,
        trainer_rows=trainer_rows,
        trainer_equipment_rows=trainer_equipment_rows,
        trainer_training_type_rows=trainer_training_type_rows,
        trainer_segment_rows=trainer_segment_rows,
        version_ids=version_ids,
        trainer_ids=trainer_ids,
        current_versions_by_exercise=current_versions_by_exercise,
        current_version_ids=current_version_ids,
    )
