"""Build validated TrainingPlanListFilters from list-query parameters."""

from typing import Annotated
from uuid import UUID

from fastapi import Query

from app.api.query_lists import parse_csv
from app.api.range_filters import reject_inverted_range
from app.schemas.training_plans import TrainingPlanListFilters


def get_training_plan_list_filters(
    name: Annotated[str | None, Query()] = None,
    min_age: Annotated[int | None, Query(ge=0)] = None,
    max_age: Annotated[int | None, Query(ge=0)] = None,
    min_participants: Annotated[int | None, Query(ge=1)] = None,
    max_participants: Annotated[int | None, Query(ge=1)] = None,
    min_duration: Annotated[int | None, Query(ge=1)] = None,
    max_duration: Annotated[int | None, Query(ge=1)] = None,
    equipment_ids: Annotated[str | None, Query()] = None,
    training_type_ids: Annotated[str | None, Query()] = None,
    training_group_ids: Annotated[str | None, Query()] = None,
) -> TrainingPlanListFilters:
    """Parse and validate list filters for GET /training-plans."""
    reject_inverted_range(min_age, max_age, label="age")
    reject_inverted_range(min_participants, max_participants, label="participants")
    reject_inverted_range(min_duration, max_duration, label="duration")
    trimmed = name.strip() if name else ""
    return TrainingPlanListFilters(
        name=trimmed or None,
        min_age=min_age,
        max_age=max_age,
        min_participants=min_participants,
        max_participants=max_participants,
        min_duration=min_duration,
        max_duration=max_duration,
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
        training_group_ids=parse_csv(
            training_group_ids,
            field_name="training_group_ids",
            parse_item=UUID,
            item_label="UUID",
        ),
    )
