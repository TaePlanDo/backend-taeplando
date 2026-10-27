"""List-query filters for GET /exercises."""

from typing import NamedTuple
from uuid import UUID


class ExerciseListFilters(NamedTuple):
    """Normalized filters applied to a trainer's exercise list."""

    name: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    min_participants: int | None = None
    max_participants: int | None = None
    equipment_ids: list[UUID] | None = None
    training_type_ids: list[UUID] | None = None
    segment_ids: list[int] | None = None


EMPTY_EXERCISE_LIST_FILTERS = ExerciseListFilters()
