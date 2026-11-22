"""Pure hard constraints shared by candidates, evolution, and persist validation."""

from collections.abc import Collection, Sequence
from uuid import UUID

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_domain import PlanExerciseSelection


def duration_bounds(
    default_minutes: int, deviation_percent: int = 20
) -> tuple[int, int]:
    """Round the allowed deviation to minutes; zero disables duration changes."""
    if default_minutes == 1 or deviation_percent == 0:
        return (default_minutes, default_minutes)
    deviation = max(1, (default_minutes * deviation_percent + 50) // 100)
    return (max(1, default_minutes - deviation), default_minutes + deviation)


def has_valid_duration(
    selection: PlanExerciseSelection, deviation_percent: int = 20
) -> bool:
    minimum, maximum = duration_bounds(
        selection.candidate.default_duration_minutes, deviation_percent
    )
    return minimum <= selection.allocated_duration_minutes <= maximum


def has_unique_exercises(selections: Sequence[PlanExerciseSelection]) -> bool:
    """True when each trainer_exercise_id appears at most once."""
    exercise_ids = [selection.candidate.trainer_exercise_id for selection in selections]
    return len(exercise_ids) == len(set(exercise_ids))


def satisfies_equipment_requirement(
    *,
    mode: EquipmentRequirementMode,
    required_equipment_ids: Collection[UUID],
    available_equipment_ids: Collection[UUID],
) -> bool:
    """Apply ALL or ANY equipment requirements against the available set."""
    required = set(required_equipment_ids)
    available = set(available_equipment_ids)
    if mode == EquipmentRequirementMode.ALL:
        return required <= available
    return not required or bool(required & available)
