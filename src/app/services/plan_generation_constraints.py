"""Pure hard constraints shared by candidates, evolution, and persist validation."""

from collections.abc import Collection, Sequence
from uuid import UUID

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_domain import PlanExerciseSelection


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
