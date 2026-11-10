"""Isolated coverage for individual plan-generation fitness criteria."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.services import plan_generation_fitness
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_fitness import (
    evaluate,
    evaluate_age_coverage,
    evaluate_body_balance,
    evaluate_duration_time,
    evaluate_equipment_usage,
    evaluate_physical_difficulty,
    evaluate_technical_difficulty,
    evaluate_training_type,
)
from app.services.plan_generation_fitness_constants import (
    BODY_LOAD_SIGMA,
    BODY_UPPER_DEMAND,
    DIFFICULTY_SIGMA,
    DURATION_OVER_SIGMA_RATIO,
    DURATION_UNDER_SIGMA_RATIO,
    PHYSICAL_DIFFICULTY_DEMAND,
)
from app.services.plan_generation_fitness_math import (
    WINDOW_TIME_SIZE,
    gaussian,
    windowed_score,
)

PREFERRED_TYPE_ID = UUID("7ac590e1-2a46-4cb7-8944-803e364cc46b")
OTHER_TYPE_ID = UUID("8ac590e1-2a46-4cb7-8944-803e364cc46b")
BALL_ID = UUID("9ac590e1-2a46-4cb7-8944-803e364cc46b")
CONE_ID = UUID("aac590e1-2a46-4cb7-8944-803e364cc46b")
ROPE_ID = UUID("bac590e1-2a46-4cb7-8944-803e364cc46b")

SEGMENT_MINUTES = 30
GROUP_YEARS = 8


def _candidate(
    *training_type_ids: UUID,
    physical: int = 3,
    technical: int = 3,
    equipment: tuple[UUID, ...] = (),
    age: tuple[int, int] = (7, 14),
    loads: tuple[int, int, int] = (3, 3, 3),
) -> PlanExerciseCandidate:
    return PlanExerciseCandidate(
        trainer_exercise_id=UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b"),
        exercise_id=UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b"),
        exercise_version_id=None,
        min_age=age[0],
        max_age=age[1],
        min_participants=1,
        max_participants=20,
        default_duration_minutes=10,
        equipment_requirement_mode=EquipmentRequirementMode.ALL,
        equipment_ids=equipment,
        training_type_ids=training_type_ids,
        segment_ids=(1,),
        physical_difficulty=physical,
        technical_difficulty=technical,
        upper_body_load=loads[0],
        lower_body_load=loads[1],
        core_load=loads[2],
    )


def _individual(*genes: tuple[PlanExerciseCandidate, int]) -> PlanIndividual:
    return PlanIndividual(
        selections=tuple(
            PlanExerciseSelection(
                schema_position=1,
                candidate=candidate,
                allocated_duration_minutes=duration,
            )
            for candidate, duration in genes
        )
    )


def _context(
    preferred_training_type_id: UUID | None,
    available_equipment_ids: tuple[UUID, ...] = (),
    *,
    group_min_age: int = 7,
    group_max_age: int = 14,
) -> GenerationContext:
    return GenerationContext(
        participant_count=12,
        available_equipment_ids=available_equipment_ids,
        preferred_training_type_id=preferred_training_type_id,
        training_group_id=UUID("6ac590e1-2a46-4cb7-8944-803e364cc46b"),
        training_group_name="Grupa",
        group_min_age=group_min_age,
        group_max_age=group_max_age,
        group_duration_minutes=60,
        deadline_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
        segment=GenerationSchemaItem(position=1, segment_id=1, percentage=50),
        segment_duration_minutes=SEGMENT_MINUTES,
        candidates=(),
        random_seed=123,
    )


def _difficulty_at(mean: float) -> float:
    return gaussian(mean - PHYSICAL_DIFFICULTY_DEMAND, DIFFICULTY_SIGMA)


def _body_near(mean: float) -> float:
    return gaussian(mean - BODY_UPPER_DEMAND, BODY_LOAD_SIGMA)


def _body_gap(gap: float) -> float:
    return gaussian(gap, BODY_LOAD_SIGMA)


def _blend(window: float, segment: float) -> float:
    return (window + segment) / 2


def _avg(*parts: tuple[float, int]) -> float:
    return sum(score * minutes for score, minutes in parts) / sum(
        minutes for _, minutes in parts
    )


def _age(overlap: int, exercise: int, group: int = GROUP_YEARS) -> float:
    return (overlap / group) * (overlap / exercise)


def _duration_at(total_minutes: int, sigma: float) -> float:
    return gaussian((total_minutes - SEGMENT_MINUTES) / SEGMENT_MINUTES, sigma)


@pytest.mark.parametrize(
    ("genes", "expected"),
    [
        (((_candidate(PREFERRED_TYPE_ID), 10),) * 3, 1.0),
        (
            ((_candidate(PREFERRED_TYPE_ID, OTHER_TYPE_ID), 30), (_candidate(), 10)),
            30 / 40,
        ),
        (((_candidate(OTHER_TYPE_ID), 10), (_candidate(), 20)), 0.0),
    ],
)
def test_training_type_scores_share_of_matching_time(
    genes: tuple[tuple[PlanExerciseCandidate, int], ...], expected: float
) -> None:
    assert evaluate_training_type(
        _context(PREFERRED_TYPE_ID), _individual(*genes)
    ) == pytest.approx(expected)


def test_training_type_is_neutral_without_preference() -> None:
    assert (
        evaluate_training_type(
            _context(None), _individual((_candidate(OTHER_TYPE_ID), 10))
        )
        == 1.0
    )


@pytest.mark.parametrize(
    ("durations", "expected"),
    [
        ((10, 10, 10), _duration_at(30, DURATION_UNDER_SIGMA_RATIO)),
        ((33,), _duration_at(33, DURATION_OVER_SIGMA_RATIO)),
        ((27,), _duration_at(27, DURATION_UNDER_SIGMA_RATIO)),
        ((20, 16), _duration_at(36, DURATION_OVER_SIGMA_RATIO)),
    ],
)
def test_duration_time_penalizes_overtime_more_than_undertime(
    durations: tuple[int, ...], expected: float
) -> None:
    individual = _individual(*((_candidate(), duration) for duration in durations))
    assert evaluate_duration_time(_context(None), individual) == pytest.approx(expected)


def test_duration_time_prefers_short_plans_over_long_ones() -> None:
    short = evaluate_duration_time(_context(None), _individual((_candidate(), 27)))
    long = evaluate_duration_time(_context(None), _individual((_candidate(), 33)))
    assert short > long


@pytest.mark.parametrize(
    ("genes", "expected"),
    [
        (((2, 5), (3, 5)), _difficulty_at(2)),
        (((1, 5), (4, 5)), _difficulty_at(1)),
        (((2, 3), (3, 4)), _avg((_difficulty_at(2.4), 5), (_difficulty_at(3), 2))),
        (((3, 120),), _difficulty_at(3)),
        (
            ((2, 3), (3, 9), (1, 1)),
            _avg(
                (_difficulty_at(2.4), 5),
                (_difficulty_at(3), 5),
                (_difficulty_at(7 / 3), 3),
            ),
        ),
    ],
)
def test_physical_difficulty_scores_each_five_minute_window(
    genes: tuple[tuple[int, int], ...], expected: float
) -> None:
    individual = _individual(
        *((_candidate(physical=difficulty), duration) for difficulty, duration in genes)
    )
    assert evaluate_physical_difficulty(_context(None), individual) == pytest.approx(
        expected
    )


def test_technical_difficulty_uses_technical_attribute() -> None:
    individual = _individual(
        (_candidate(physical=5, technical=2), 5),
        (_candidate(physical=5, technical=3), 5),
    )
    assert evaluate_technical_difficulty(_context(None), individual) == pytest.approx(
        _difficulty_at(2)
    )


@pytest.mark.parametrize(
    ("equipment_by_exercise", "expected"),
    [
        (((BALL_ID,),), 1 / 2),
        (((BALL_ID,), (CONE_ID,)), 1.0),
        (((BALL_ID, CONE_ID), (BALL_ID,)), 1.0),
        (((BALL_ID, ROPE_ID),), 1 / 2),
        (((),), 0.0),
    ],
)
def test_equipment_usage_scores_share_of_available_equipment(
    equipment_by_exercise: tuple[tuple[UUID, ...], ...], expected: float
) -> None:
    individual = _individual(
        *((_candidate(equipment=equipment), 10) for equipment in equipment_by_exercise)
    )
    assert evaluate_equipment_usage(
        _context(None, available_equipment_ids=(BALL_ID, CONE_ID)), individual
    ) == pytest.approx(expected)


def test_equipment_usage_is_neutral_without_available_equipment() -> None:
    assert (
        evaluate_equipment_usage(
            _context(None), _individual((_candidate(equipment=(BALL_ID,)), 10))
        )
        == 1.0
    )


@pytest.mark.parametrize(
    ("genes", "expected"),
    [
        ((((7, 14), 10),), _age(8, 8)),
        ((((5, 20), 10),), _age(8, 16)),
        ((((7, 10), 10),), _age(4, 4)),
        ((((12, 30), 10),), _age(3, 19)),
        ((((7, 14), 30), ((11, 14), 10)), _avg((_age(8, 8), 30), (_age(4, 4), 10))),
        ((((1, 99), 10),), _age(8, 99)),
    ],
)
def test_age_coverage_scores_coverage_times_specificity(
    genes: tuple[tuple[tuple[int, int], int], ...], expected: float
) -> None:
    individual = _individual(
        *((_candidate(age=age), minutes) for age, minutes in genes)
    )
    assert evaluate_age_coverage(_context(None), individual) == pytest.approx(expected)


def test_age_coverage_prefers_kids_specific_range_over_catch_all() -> None:
    context = _context(None, group_min_age=3, group_max_age=6)
    kids = evaluate_age_coverage(context, _individual((_candidate(age=(1, 6)), 10)))
    catch_all = evaluate_age_coverage(
        context, _individual((_candidate(age=(1, 99)), 10))
    )
    exact = evaluate_age_coverage(context, _individual((_candidate(age=(3, 6)), 10)))

    assert kids == pytest.approx(_age(4, 6, group=4))
    assert catch_all == pytest.approx(_age(4, 99, group=4))
    assert exact == pytest.approx(1.0)
    assert exact > kids > catch_all


@pytest.mark.parametrize(
    ("genes", "expected"),
    [
        ((), 0.0),
        ((((3,), 5),), 3.0),
        ((((2,), 3), ((4,), 2)), 2.8),
        ((((1,), 7), ((5,), 3)), _avg((1.0, 5), (3.4, 5))),
    ],
)
def test_windowed_score_chunks_timeline_into_five_minute_windows(
    genes: tuple[tuple[tuple[int, ...], int], ...], expected: float
) -> None:
    assert WINDOW_TIME_SIZE == 5
    individual = _individual(
        *((_candidate(physical=values[0]), minutes) for values, minutes in genes)
    )
    assert windowed_score(
        individual,
        lambda candidate: (candidate.physical_difficulty,),
        lambda means: means[0],
    ) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("genes", "expected"),
    [
        ((((3, 3, 3), 10),), _blend(_body_gap(0), _body_near(3))),
        (
            (((3, 2, 2), 10),),
            _blend(_body_gap(1), (_body_near(3) + _body_near(2) + _body_near(2)) / 3),
        ),
        ((((5, 1, 3), 5), ((1, 5, 3), 5)), _blend(_body_gap(4), _body_near(3))),
        (
            (((4, 2, 3), 3), ((2, 4, 3), 2)),
            _blend(
                _body_gap(0.4),
                (_body_near(3.2) + _body_near(2.8) + _body_near(3.0)) / 3,
            ),
        ),
    ],
)
def test_body_balance_scores_windows_and_whole_segment(
    genes: tuple[tuple[tuple[int, int, int], int], ...], expected: float
) -> None:
    individual = _individual(
        *((_candidate(loads=loads), minutes) for loads, minutes in genes)
    )
    assert evaluate_body_balance(_context(None), individual) == pytest.approx(expected)


def test_evaluate_returns_weighted_mean_of_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        plan_generation_fitness,
        "FITNESS_CRITERIA",
        (
            (lambda context, individual: 1.0, 3.0),
            (lambda context, individual: 0.0, 1.0),
        ),
    )
    assert evaluate(_context(None), _individual((_candidate(), 30))) == 3 / 4


def test_evaluate_stays_in_unit_range() -> None:
    individual = _individual(
        (_candidate(physical=2, loads=(4, 2, 3)), 12),
        (_candidate(physical=3, age=(10, 18)), 18),
    )
    assert 0.0 <= evaluate(_context(None), individual) <= 1.0
