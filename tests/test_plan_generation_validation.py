"""Hard pre-persist validation for generated training plans."""

from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_domain import (
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_errors import InvalidGeneratedPlanError
from app.services.plan_generation_validation import validate_generated_plan

EQUIPMENT_A = UUID("2ac590e1-2a46-4cb7-8944-803e364cc46b")
EQUIPMENT_B = UUID("3ac590e1-2a46-4cb7-8944-803e364cc46b")


def _candidate(
    identifier: str,
    *,
    segment_ids: tuple[int, ...] = (1,),
    min_age: int = 7,
    max_age: int = 14,
    min_participants: int = 1,
    max_participants: int = 20,
    equipment_ids: tuple[UUID, ...] = (),
    equipment_mode: EquipmentRequirementMode = EquipmentRequirementMode.ALL,
) -> PlanExerciseCandidate:
    return PlanExerciseCandidate(
        trainer_exercise_id=UUID(identifier),
        exercise_id=UUID(identifier),
        exercise_version_id=None,
        min_age=min_age,
        max_age=max_age,
        min_participants=min_participants,
        max_participants=max_participants,
        default_duration_minutes=10,
        equipment_requirement_mode=equipment_mode,
        equipment_ids=equipment_ids,
        training_type_ids=(),
        segment_ids=segment_ids,
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        recent_usage_distance=4,
    )


def _plan(
    *items: tuple[int, PlanExerciseCandidate, int],
) -> PlanIndividual:
    return PlanIndividual(
        selections=tuple(
            PlanExerciseSelection(
                schema_position=position,
                candidate=candidate,
                allocated_duration_minutes=duration,
            )
            for position, candidate, duration in items
        )
    )


def _validate(
    plan: PlanIndividual,
    *,
    segment_by_position: dict[int, int] | None = None,
    group_min_age: int = 7,
    group_max_age: int = 14,
    participant_count: int = 12,
    available_equipment_ids: tuple[UUID, ...] = (),
) -> None:
    validate_generated_plan(
        segment_by_position=segment_by_position or {1: 1},
        group_min_age=group_min_age,
        group_max_age=group_max_age,
        participant_count=participant_count,
        available_equipment_ids=available_equipment_ids,
        plan=plan,
    )


def test_validate_generated_plan_accepts_a_valid_plan() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", segment_ids=(1, 2))
    second = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", segment_ids=(2,))

    _validate(
        _plan((1, candidate, 20), (2, second, 15)),
        segment_by_position={1: 1, 2: 2},
    )


def test_validate_generated_plan_rejects_missing_schema_position() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")

    with pytest.raises(InvalidGeneratedPlanError) as error:
        _validate(_plan((1, candidate, 10)), segment_by_position={1: 1, 2: 2})

    assert error.value.error_code == "INVALID_GENERATED_PLAN"
    assert str(error.value) == (
        "Generated plan does not meet requirements and was not saved."
    )
    assert error.value.reason is not None
    assert "missing" in error.value.reason


def test_validate_generated_plan_rejects_unknown_schema_position() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")

    with pytest.raises(InvalidGeneratedPlanError, match="requirements"):
        _validate(
            _plan((1, candidate, 10), (3, candidate, 10)),
            segment_by_position={1: 1},
        )


def test_validate_generated_plan_rejects_wrong_segment_membership() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", segment_ids=(2,))

    with pytest.raises(InvalidGeneratedPlanError) as error:
        _validate(_plan((1, candidate, 10)))

    assert "segment" in (error.value.reason or "")


def test_validate_generated_plan_rejects_incompatible_age() -> None:
    candidate = _candidate(
        "0ac590e1-2a46-4cb7-8944-803e364cc46b", min_age=15, max_age=18
    )

    with pytest.raises(InvalidGeneratedPlanError) as error:
        _validate(_plan((1, candidate, 10)), group_min_age=7, group_max_age=14)

    assert "age" in (error.value.reason or "")


def test_validate_generated_plan_rejects_incompatible_participants() -> None:
    candidate = _candidate(
        "0ac590e1-2a46-4cb7-8944-803e364cc46b",
        min_participants=2,
        max_participants=8,
    )

    with pytest.raises(InvalidGeneratedPlanError) as error:
        _validate(_plan((1, candidate, 10)), participant_count=12)

    assert "participant" in (error.value.reason or "")


def test_validate_generated_plan_rejects_unmet_equipment() -> None:
    candidate = _candidate(
        "0ac590e1-2a46-4cb7-8944-803e364cc46b",
        equipment_ids=(EQUIPMENT_A, EQUIPMENT_B),
        equipment_mode=EquipmentRequirementMode.ALL,
    )

    with pytest.raises(InvalidGeneratedPlanError) as error:
        _validate(
            _plan((1, candidate, 10)),
            available_equipment_ids=(EQUIPMENT_A,),
        )

    assert "equipment" in (error.value.reason or "")


def test_validate_generated_plan_rejects_non_positive_duration() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")

    with pytest.raises(InvalidGeneratedPlanError) as error:
        _validate(_plan((1, candidate, 0)))

    assert "duration" in (error.value.reason or "")


def test_validate_generated_plan_rejects_duplicate_exercises_in_segment() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")

    with pytest.raises(InvalidGeneratedPlanError) as error:
        _validate(_plan((1, candidate, 5), (1, candidate, 5)))

    assert "duplicate" in (error.value.reason or "")


def test_validate_generated_plan_allows_short_and_long_totals() -> None:
    """Duration vs target is soft fitness; short/long plans still pass hard rules."""
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")
    second = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", segment_ids=(2,))
    positions = {1: 1, 2: 2}

    _validate(_plan((1, candidate, 1), (2, second, 1)), segment_by_position=positions)
    _validate(
        _plan((1, candidate, 90), (2, second, 90)),
        segment_by_position=positions,
    )
