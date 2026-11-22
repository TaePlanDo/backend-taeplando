"""Shared snapshot filling for historical plan-exercise rows."""

from collections.abc import Sequence

from app.models.catalogs import Equipment, TrainingType
from app.models.exercises import TrainerExercise
from app.models.training import TrainingPlanExercise


def fill_plan_exercise_from_source(
    exercise: TrainingPlanExercise,
    source: TrainerExercise,
    *,
    duration_minutes: int,
) -> None:
    """Copy identity and frozen display fields from one trainer configuration."""
    details = source.source_version or source.exercise
    exercise.trainer_exercise_id = source.id
    exercise.exercise_id = source.exercise_id
    exercise.exercise_version_id = source.source_version_id
    exercise.name_snapshot = details.name
    exercise.description_snapshot = details.description
    exercise.image_url_snapshot = details.image_url
    exercise.min_age_snapshot = source.min_age
    exercise.max_age_snapshot = source.max_age
    exercise.min_participants_snapshot = source.min_participants
    exercise.max_participants_snapshot = source.max_participants
    exercise.duration_minutes_snapshot = duration_minutes
    exercise.physical_difficulty_snapshot = source.physical_difficulty
    exercise.technical_difficulty_snapshot = source.technical_difficulty
    exercise.upper_body_load_snapshot = source.upper_body_load
    exercise.lower_body_load_snapshot = source.lower_body_load
    exercise.core_load_snapshot = source.core_load
    exercise.equipment_snapshot = catalog_snapshot(source.equipment)
    exercise.training_types_snapshot = catalog_snapshot(source.training_types)
    exercise.segments_snapshot = [
        {"id": segment.id, "code": segment.code, "name": segment.name}
        for segment in sorted(source.segments, key=lambda segment: segment.id)
    ]


def catalog_snapshot(
    items: Sequence[Equipment | TrainingType],
) -> list[dict[str, object]]:
    """Freeze catalog items as sorted id/name pairs for JSONB snapshots."""
    return [
        {"id": str(item.id), "name": item.name}
        for item in sorted(items, key=lambda item: (item.name, item.id))
    ]
