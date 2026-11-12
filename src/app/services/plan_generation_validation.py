"""Hard validation gate for a generated plan before it is persisted."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import NoReturn
from uuid import UUID

from app.services.plan_generation_constraints import (
    has_unique_exercises,
    satisfies_equipment_requirement,
)
from app.services.plan_generation_domain import PlanExerciseSelection, PlanIndividual
from app.services.plan_generation_errors import InvalidGeneratedPlanError

logger = logging.getLogger(__name__)


def validate_generated_plan(
    *,
    segment_by_position: Mapping[int, int],
    group_min_age: int,
    group_max_age: int,
    participant_count: int,
    available_equipment_ids: Sequence[UUID],
    plan: PlanIndividual,
) -> None:
    """Reject plans that violate hard generation rules before snapshot persist."""
    required = set(segment_by_position)
    present = {selection.schema_position for selection in plan.selections}
    if missing := required - present:
        _reject(f"missing schema positions {sorted(missing)}")
    if unknown := present - required:
        _reject(f"unknown schema positions {sorted(unknown)}")

    available = set(available_equipment_ids)
    for position, selections in _by_position(plan).items():
        if not has_unique_exercises(selections):
            _reject(f"duplicate exercises in schema position {position}")
        segment_id = segment_by_position[position]
        for selection in selections:
            _validate_selection(
                selection,
                segment_id=segment_id,
                group_min_age=group_min_age,
                group_max_age=group_max_age,
                participant_count=participant_count,
                available_equipment_ids=available,
            )


def _reject(reason: str) -> NoReturn:
    logger.info("generated plan rejected: %s", reason)
    raise InvalidGeneratedPlanError(reason)


def _by_position(plan: PlanIndividual) -> dict[int, list[PlanExerciseSelection]]:
    grouped: dict[int, list[PlanExerciseSelection]] = defaultdict(list)
    for selection in plan.selections:
        grouped[selection.schema_position].append(selection)
    return grouped


def _validate_selection(
    selection: PlanExerciseSelection,
    *,
    segment_id: int,
    group_min_age: int,
    group_max_age: int,
    participant_count: int,
    available_equipment_ids: set[UUID],
) -> None:
    position = selection.schema_position
    if selection.allocated_duration_minutes < 1:
        _reject(f"non-positive duration at schema position {position}")
    candidate = selection.candidate
    if segment_id not in candidate.segment_ids:
        _reject(f"exercise does not belong to segment for schema position {position}")
    if candidate.max_age < group_min_age or candidate.min_age > group_max_age:
        _reject(f"exercise age range incompatible at schema position {position}")
    if not (
        candidate.min_participants <= participant_count <= candidate.max_participants
    ):
        _reject(
            f"exercise participant range incompatible at schema position {position}"
        )
    if not satisfies_equipment_requirement(
        mode=candidate.equipment_requirement_mode,
        required_equipment_ids=candidate.equipment_ids,
        available_equipment_ids=available_equipment_ids,
    ):
        _reject(f"exercise equipment requirements unmet at schema position {position}")
