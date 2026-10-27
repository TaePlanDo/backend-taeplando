"""Build validated ExerciseListFilters from list-query parameters."""

from typing import Annotated
from uuid import UUID

from fastapi import HTTPException, Query, status

from app.api.query_lists import parse_csv
from app.schemas.exercise_list_filters import ExerciseListFilters


def _reject_inverted_range(
    min_value: int | None, max_value: int | None, *, label: str
) -> None:
    """Reject impossible inclusive filter ranges when both bounds are set."""
    if min_value is not None and max_value is not None and min_value > max_value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"min_{label} must be less than or equal to max_{label}",
        )


def get_exercise_list_filters(
    name: Annotated[str | None, Query()] = None,
    min_age: Annotated[int | None, Query(ge=0)] = None,
    max_age: Annotated[int | None, Query(ge=0)] = None,
    min_participants: Annotated[int | None, Query(ge=1)] = None,
    max_participants: Annotated[int | None, Query(ge=1)] = None,
    equipment_ids: Annotated[str | None, Query()] = None,
    training_type_ids: Annotated[str | None, Query()] = None,
    segment_ids: Annotated[str | None, Query()] = None,
) -> ExerciseListFilters:
    """Parse and validate list filters for GET /exercises."""
    _reject_inverted_range(min_age, max_age, label="age")
    _reject_inverted_range(min_participants, max_participants, label="participants")
    trimmed = name.strip() if name else ""
    return ExerciseListFilters(
        name=trimmed or None,
        min_age=min_age,
        max_age=max_age,
        min_participants=min_participants,
        max_participants=max_participants,
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
