"""List-query filters for GET /exercises."""

from typing import NamedTuple
from uuid import UUID

from app.models.enums import TrainerExerciseStatus


class ExerciseListFilters(NamedTuple):
    """Normalized filters applied to a trainer's exercise list."""

    name: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    min_participants: int | None = None
    max_participants: int | None = None
    min_physical_difficulty: int | None = None
    max_physical_difficulty: int | None = None
    min_technical_difficulty: int | None = None
    max_technical_difficulty: int | None = None
    min_upper_body_load: int | None = None
    max_upper_body_load: int | None = None
    min_lower_body_load: int | None = None
    max_lower_body_load: int | None = None
    min_core_load: int | None = None
    max_core_load: int | None = None
    status: TrainerExerciseStatus | None = None
    equipment_ids: list[UUID] | None = None
    training_type_ids: list[UUID] | None = None
    segment_ids: list[int] | None = None


EMPTY_EXERCISE_LIST_FILTERS = ExerciseListFilters()
