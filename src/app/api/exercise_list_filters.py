"""Build validated ExerciseListFilters from list-query parameters."""

from typing import Annotated
from uuid import UUID

from fastapi import Query

from app.api.query_lists import parse_csv
from app.api.range_filters import reject_inverted_range
from app.models.enums import TrainerExerciseStatus
from app.schemas.exercise_list_filters import ExerciseListFilters


def get_exercise_list_filters(
    name: Annotated[str | None, Query()] = None,
    min_age: Annotated[int | None, Query(ge=0)] = None,
    max_age: Annotated[int | None, Query(ge=0)] = None,
    min_participants: Annotated[int | None, Query(ge=1)] = None,
    max_participants: Annotated[int | None, Query(ge=1)] = None,
    min_physical_difficulty: Annotated[int | None, Query(ge=1, le=5)] = None,
    max_physical_difficulty: Annotated[int | None, Query(ge=1, le=5)] = None,
    min_technical_difficulty: Annotated[int | None, Query(ge=1, le=5)] = None,
    max_technical_difficulty: Annotated[int | None, Query(ge=1, le=5)] = None,
    min_upper_body_load: Annotated[int | None, Query(ge=1, le=5)] = None,
    max_upper_body_load: Annotated[int | None, Query(ge=1, le=5)] = None,
    min_lower_body_load: Annotated[int | None, Query(ge=1, le=5)] = None,
    max_lower_body_load: Annotated[int | None, Query(ge=1, le=5)] = None,
    min_core_load: Annotated[int | None, Query(ge=1, le=5)] = None,
    max_core_load: Annotated[int | None, Query(ge=1, le=5)] = None,
    status: Annotated[TrainerExerciseStatus | None, Query()] = None,
    equipment_ids: Annotated[str | None, Query()] = None,
    training_type_ids: Annotated[str | None, Query()] = None,
    segment_ids: Annotated[str | None, Query()] = None,
) -> ExerciseListFilters:
    """Parse and validate list filters for GET /exercises."""
    reject_inverted_range(min_age, max_age, label="age")
    reject_inverted_range(min_participants, max_participants, label="participants")
    for label, minimum, maximum in (
        ("physical_difficulty", min_physical_difficulty, max_physical_difficulty),
        ("technical_difficulty", min_technical_difficulty, max_technical_difficulty),
        ("upper_body_load", min_upper_body_load, max_upper_body_load),
        ("lower_body_load", min_lower_body_load, max_lower_body_load),
        ("core_load", min_core_load, max_core_load),
    ):
        reject_inverted_range(minimum, maximum, label=label)
    trimmed = name.strip() if name else ""
    return ExerciseListFilters(
        name=trimmed or None,
        min_age=min_age,
        max_age=max_age,
        min_participants=min_participants,
        max_participants=max_participants,
        min_physical_difficulty=min_physical_difficulty,
        max_physical_difficulty=max_physical_difficulty,
        min_technical_difficulty=min_technical_difficulty,
        max_technical_difficulty=max_technical_difficulty,
        min_upper_body_load=min_upper_body_load,
        max_upper_body_load=max_upper_body_load,
        min_lower_body_load=min_lower_body_load,
        max_lower_body_load=max_lower_body_load,
        min_core_load=min_core_load,
        max_core_load=max_core_load,
        status=status,
        equipment_ids=parse_csv(
            equipment_ids,
            field_name="equipment_ids",
            parse_item=UUID,
            item_label="UUID",
        ),
        training_type_ids=parse_csv(
            training_type_ids,
            field_name="training_type_ids",
            parse_item=UUID,
            item_label="UUID",
        ),
        segment_ids=parse_csv(
            segment_ids,
            field_name="segment_ids",
            parse_item=int,
            item_label="integer",
        ),
    )
